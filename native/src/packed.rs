//! General multiword F2 rows. Stable pivots never permute original coordinates.
use pyo3::exceptions::{PyMemoryError, PyValueError};
use pyo3::prelude::*;
use std::time::Instant;

#[derive(Clone)]
struct Packed {
    m: usize,
    n: usize,
    words: usize,
    data: Vec<u64>,
}

fn zeros(size: usize) -> PyResult<Vec<u64>> {
    let mut data = Vec::new();
    data.try_reserve_exact(size)
        .map_err(|_| PyMemoryError::new_err("packed allocation failed"))?;
    data.resize(size, 0);
    Ok(data)
}

fn checked_vector(vector: &[u64], n: usize) -> PyResult<()> {
    let words = n.div_ceil(64);
    if vector.len() != words
        || (!n.is_multiple_of(64) && vector.last().is_some_and(|word| word >> (n % 64) != 0))
    {
        return Err(PyValueError::new_err(
            "packed shape or nonzero padding bits",
        ));
    }
    Ok(())
}

impl Packed {
    fn zero(m: usize, n: usize) -> PyResult<Self> {
        let words = n.div_ceil(64);
        let size = m
            .checked_mul(words)
            .ok_or_else(|| PyMemoryError::new_err("packed size overflow"))?;
        Ok(Self {
            m,
            n,
            words,
            data: zeros(size)?,
        })
    }

    fn new(rows: Vec<Vec<u64>>, n: usize) -> PyResult<Self> {
        for row in &rows {
            checked_vector(row, n)?;
        }
        let mut matrix = Self::zero(rows.len(), n)?;
        for (i, row) in rows.iter().enumerate() {
            matrix.data[i * matrix.words..(i + 1) * matrix.words].copy_from_slice(row);
        }
        Ok(matrix)
    }

    fn row(&self, i: usize) -> &[u64] {
        &self.data[i * self.words..(i + 1) * self.words]
    }
    fn rows(&self) -> Vec<Vec<u64>> {
        (0..self.m).map(|i| self.row(i).to_vec()).collect()
    }
    fn bit(&self, i: usize, j: usize) -> bool {
        self.data[i * self.words + j / 64] >> (j % 64) & 1 != 0
    }
    fn set(&mut self, i: usize, j: usize) {
        self.data[i * self.words + j / 64] |= 1_u64 << (j % 64);
    }
    fn nnz(&self) -> usize {
        self.data
            .iter()
            .map(|word| word.count_ones() as usize)
            .sum()
    }
    fn swap(&mut self, i: usize, j: usize) {
        for word in 0..self.words {
            self.data.swap(i * self.words + word, j * self.words + word);
        }
    }
    fn xor_row(&mut self, i: usize, j: usize) -> (usize, usize) {
        let mut before = 0;
        let mut after = 0;
        for word in 0..self.words {
            let index = i * self.words + word;
            before += self.data[index].count_ones() as usize;
            self.data[index] ^= self.data[j * self.words + word];
            after += self.data[index].count_ones() as usize;
        }
        (before, after)
    }
    fn apply(&self, x: &[u64]) -> PyResult<Vec<u64>> {
        checked_vector(x, self.n)?;
        let mut output = zeros(self.m.div_ceil(64))?;
        self.apply_into(x, &mut output);
        Ok(output)
    }
    fn apply_into(&self, x: &[u64], output: &mut [u64]) {
        output.fill(0);
        for i in 0..self.m {
            let parity = self
                .row(i)
                .iter()
                .zip(x)
                .fold(0, |p, (a, b)| p ^ ((a & b).count_ones() & 1));
            output[i / 64] |= u64::from(parity) << (i % 64);
        }
    }
}

#[pyfunction]
pub fn packed_add(
    a: Vec<Vec<u64>>,
    an: usize,
    b: Vec<Vec<u64>>,
    bn: usize,
) -> PyResult<Vec<Vec<u64>>> {
    let a = Packed::new(a, an)?;
    let mut b = Packed::new(b, bn)?;
    if a.m != b.m || a.n != b.n {
        return Err(PyValueError::new_err("addition requires equal shapes"));
    }
    for (x, y) in a.data.iter().zip(&mut b.data) {
        *y ^= x;
    }
    Ok(b.rows())
}

#[pyfunction]
pub fn packed_product(
    a: Vec<Vec<u64>>,
    an: usize,
    b: Vec<Vec<u64>>,
    bn: usize,
) -> PyResult<Vec<Vec<u64>>> {
    let a = Packed::new(a, an)?;
    let b = Packed::new(b, bn)?;
    if a.n != b.m {
        return Err(PyValueError::new_err("product inner dimensions differ"));
    }
    let mut output = Packed::zero(a.m, b.n)?;
    for i in 0..a.m {
        for (word, &bits) in a.row(i).iter().enumerate() {
            let mut remaining = bits;
            while remaining != 0 {
                let j = word * 64 + remaining.trailing_zeros() as usize;
                for k in 0..b.words {
                    output.data[i * b.words + k] ^= b.row(j)[k];
                }
                remaining &= remaining - 1;
            }
        }
    }
    Ok(output.rows())
}

#[pyclass(frozen)]
pub struct PreparedMatrix {
    original: Packed,
    reduced: Packed,
    transform: Packed,
    pivots: Vec<usize>,
    peak_nnz: usize,
}

#[pymethods]
impl PreparedMatrix {
    #[new]
    #[pyo3(signature=(rows, ncols, cancellation=None))]
    fn new(
        py: Python<'_>,
        rows: Vec<Vec<u64>>,
        ncols: usize,
        cancellation: Option<PyRef<'_, super::CancellationFlag>>,
    ) -> PyResult<Self> {
        let cancellation = cancellation.map(|flag| flag.state.clone());
        py.detach(move || {
            let original = Packed::new(rows, ncols)?;
            let started = Instant::now();
            checkpoint(0, None, started, None, &cancellation)?;
            let mut reduced = original.clone();
            let mut transform = Packed::zero(original.m, original.m)?;
            for i in 0..original.m {
                transform.set(i, i);
            }
            let mut pivots = Vec::new();
            let mut nnz = reduced.nnz();
            let mut peak_nnz = nnz;
            for col in 0..original.n {
                checkpoint(0, None, started, None, &cancellation)?;
                let pivot_row = pivots.len();
                if let Some(selected) = (pivot_row..original.m).find(|&row| reduced.bit(row, col)) {
                    reduced.swap(pivot_row, selected);
                    transform.swap(pivot_row, selected);
                    for row in 0..original.m {
                        checkpoint(0, None, started, None, &cancellation)?;
                        if row != pivot_row && reduced.bit(row, col) {
                            let (before, after) = reduced.xor_row(row, pivot_row);
                            nnz = nnz - before + after;
                            peak_nnz = peak_nnz.max(nnz);
                            transform.xor_row(row, pivot_row);
                        }
                    }
                    pivots.push(col);
                    if pivots.len() == original.m {
                        break;
                    }
                }
            }
            Ok(Self {
                original,
                reduced,
                transform,
                pivots,
                peak_nnz,
            })
        })
    }

    #[getter]
    fn nrows(&self) -> usize {
        self.original.m
    }
    #[getter]
    fn ncols(&self) -> usize {
        self.original.n
    }
    #[getter]
    fn pivots(&self) -> Vec<usize> {
        self.pivots.clone()
    }
    #[getter]
    fn decomposition_count(&self) -> usize {
        1
    }
    #[getter]
    fn source_nonzero_bits(&self) -> usize {
        self.original.nnz()
    }
    #[getter]
    fn reduced_nonzero_bits(&self) -> usize {
        self.reduced.nnz()
    }
    #[getter]
    fn peak_nonzero_bits(&self) -> usize {
        self.peak_nnz
    }
    #[getter]
    fn stored_words(&self) -> usize {
        self.original.data.len() + self.reduced.data.len() + self.transform.data.len()
    }

    fn rank(&self) -> usize {
        self.pivots.len()
    }

    fn inverse_rows(&self) -> PyResult<Vec<Vec<u64>>> {
        // Continue the reference RREF through the RIGHT side of [M | I].
        // Its null coefficient rows can change the upper inverse rows.
        let mut transform = self.transform.clone();
        let mut pivot_row = self.pivots.len();
        for col in 0..self.original.m {
            if let Some(selected) = (pivot_row..self.original.m).find(|&i| transform.bit(i, col)) {
                transform.swap(pivot_row, selected);
                for i in 0..self.original.m {
                    if i != pivot_row && transform.bit(i, col) {
                        transform.xor_row(i, pivot_row);
                    }
                }
                pivot_row += 1;
                if pivot_row == self.original.m {
                    break;
                }
            }
        }
        Ok((0..self.pivots.len())
            .map(|i| transform.row(i).to_vec())
            .collect())
    }
    fn rref(&self) -> Vec<Vec<u64>> {
        self.reduced.rows()
    }

    fn kernel_basis(&self) -> PyResult<Vec<Vec<u64>>> {
        let mut basis = Packed::zero(self.original.n - self.pivots.len(), self.original.n)?;
        let mut row = 0;
        for free in 0..self.original.n {
            if self.pivots.binary_search(&free).is_ok() {
                continue;
            }
            basis.set(row, free);
            for (i, &pivot) in self.pivots.iter().enumerate() {
                if self.reduced.bit(i, free) {
                    basis.set(row, pivot);
                }
            }
            row += 1;
        }
        Ok(basis.rows())
    }

    fn image_basis(&self) -> PyResult<Vec<Vec<u64>>> {
        let mut basis = Packed::zero(self.pivots.len(), self.original.m)?;
        for (i, &pivot) in self.pivots.iter().enumerate() {
            for j in 0..self.original.m {
                if self.original.bit(j, pivot) {
                    basis.set(i, j);
                }
            }
        }
        Ok(basis.rows())
    }

    fn apply_many(&self, vectors: Vec<Vec<u64>>) -> PyResult<Vec<Vec<u64>>> {
        vectors.iter().map(|x| self.original.apply(x)).collect()
    }

    fn solve_many(&self, vectors: Vec<Vec<u64>>) -> PyResult<Vec<Option<Vec<u64>>>> {
        let mut output = Vec::with_capacity(vectors.len());
        for x in vectors {
            let y = self.transform.apply(&x)?;
            if (self.pivots.len()..self.original.m).any(|i| y[i / 64] >> (i % 64) & 1 != 0) {
                output.push(None);
                continue;
            }
            let mut solution = zeros(self.original.words)?;
            for (row, &pivot) in self.pivots.iter().enumerate() {
                solution[pivot / 64] |= ((y[row / 64] >> (row % 64)) & 1) << (pivot % 64);
            }
            output.push(Some(solution));
        }
        Ok(output)
    }

    fn membership_many(&self, vectors: Vec<Vec<u64>>) -> PyResult<Vec<bool>> {
        let mut output = Vec::with_capacity(vectors.len());
        for x in vectors {
            let y = self.transform.apply(&x)?;
            output.push(
                !(self.pivots.len()..self.original.m).any(|i| y[i / 64] >> (i % 64) & 1 != 0),
            );
        }
        Ok(output)
    }
}

type CompactBatch = (Vec<Vec<u64>>, Vec<Vec<u64>>, Vec<Vec<usize>>, f64);

// Private reusable buffers belong to this query workspace, never to an operator.
// The binding adapter ties the prepared action, boundary and weights to six IDs.
#[pyclass]
pub struct GeometryWorkspace {
    boundary: Packed,
    factors: Vec<Packed>,
    pivots: Vec<Vec<usize>>,
    form: String,
    complement: bool,
    weights: Option<Vec<u64>>,
    n: usize,
    cycle_image: Vec<u64>,
    a_image: Vec<u64>,
    coefficients: Vec<u64>,
    retracted: Vec<u64>,
    boundary_coefficients: Vec<u64>,
    projected_one: Vec<u64>,
    projected: Vec<u64>,
    batches: usize,
    buffer_growths: usize,
}

type GeometryBatch = (
    Vec<Vec<u64>>,
    Vec<Vec<usize>>,
    Vec<Option<u64>>,
    Vec<Option<u64>>,
    Vec<Vec<usize>>,
    Vec<Vec<usize>>,
    Vec<Vec<usize>>,
    f64,
);

fn support(bits: &[u64]) -> Vec<usize> {
    let mut indices = Vec::new();
    for (word, &value) in bits.iter().enumerate() {
        let mut remaining = value;
        while remaining != 0 {
            indices.push(64 * word + remaining.trailing_zeros() as usize);
            remaining &= remaining - 1;
        }
    }
    indices
}

fn checked_mass(weights: &Option<Vec<u64>>, indices: &[usize]) -> Option<u64> {
    let weights = weights.as_ref()?;
    indices
        .iter()
        .try_fold(0_u64, |total, &i| total.checked_add(weights[i]))
}

#[pymethods]
impl GeometryWorkspace {
    #[new]
    fn new(
        boundary: Vec<Vec<u64>>,
        form: String,
        rows: Vec<Vec<Vec<u64>>>,
        columns: Vec<usize>,
        pivots: Vec<Vec<usize>>,
        complement: bool,
        weights: Option<Vec<u64>>,
    ) -> PyResult<Self> {
        if rows.len() != columns.len() {
            return Err(PyValueError::new_err("geometry factor shapes differ"));
        }
        let factors = rows
            .into_iter()
            .zip(columns)
            .map(|(r, n)| Packed::new(r, n))
            .collect::<PyResult<Vec<_>>>()?;
        let n = match form.as_str() {
            "Matrix" if factors.len() == 1 && pivots.is_empty() && factors[0].n == factors[0].m => {
                factors[0].n
            }
            "HC" if factors.len() == 2
                && pivots.is_empty()
                && factors[0].m == factors[1].n
                && factors[0].n == factors[1].m =>
            {
                factors[0].m
            }
            "GeneralizedInverse" if factors.len() == 4 && pivots.len() == 2 => {
                let (a, d, g, u) = (&factors[0], &factors[1], &factors[2], &factors[3]);
                if a.n != d.m
                    || g.m != pivots[0].len()
                    || g.n != a.m
                    || u.m != pivots[1].len()
                    || u.n != d.m
                {
                    return Err(PyValueError::new_err("geometry inverse shapes differ"));
                }
                for (indices, limit) in pivots.iter().zip([a.n, d.n]) {
                    if indices.iter().any(|&i| i >= limit)
                        || indices.windows(2).any(|p| p[0] >= p[1])
                    {
                        return Err(PyValueError::new_err("invalid geometry pivots"));
                    }
                }
                a.n
            }
            _ => return Err(PyValueError::new_err("unsupported geometry action")),
        };
        let boundary = Packed::new(boundary, n)?;
        if weights
            .as_ref()
            .is_some_and(|w| w.len() != n || w.contains(&0))
        {
            return Err(PyValueError::new_err(
                "geometry requires n positive weights",
            ));
        }
        let a_size = if form == "GeneralizedInverse" {
            factors[0].m
        } else {
            0
        };
        let coefficient_size = match form.as_str() {
            "GeneralizedInverse" => factors[2].m.max(factors[3].m),
            "HC" => factors[1].m,
            _ => 0,
        };
        let d_size = if form == "GeneralizedInverse" {
            factors[1].n
        } else {
            0
        };
        Ok(Self {
            cycle_image: zeros(boundary.m.div_ceil(64))?,
            a_image: zeros(a_size.div_ceil(64))?,
            coefficients: zeros(coefficient_size.div_ceil(64))?,
            retracted: zeros(n.div_ceil(64))?,
            boundary_coefficients: zeros(d_size.div_ceil(64))?,
            projected_one: zeros(n.div_ceil(64))?,
            boundary,
            factors,
            pivots,
            form,
            complement,
            weights,
            n,
            projected: Vec::new(),
            batches: 0,
            buffer_growths: 0,
        })
    }

    fn statistics(&self) -> (usize, usize, usize) {
        (self.batches, self.buffer_growths, self.projected.capacity())
    }

    #[pyo3(signature=(vectors, pairs, cancellation=None, state_limit=None, wall=None))]
    fn query(
        &mut self,
        py: Python<'_>,
        vectors: Vec<Vec<u64>>,
        pairs: Vec<(usize, usize)>,
        cancellation: Option<PyRef<'_, super::CancellationFlag>>,
        state_limit: Option<usize>,
        wall: Option<f64>,
    ) -> PyResult<GeometryBatch> {
        check_wall(wall)?;
        let cancellation = cancellation.map(|flag| flag.state.clone());
        py.detach(move || {
            let started = Instant::now();
            // Reject the entire batch before producing or retaining any new Pz.
            for x in &vectors {
                checked_vector(x, self.n)?;
                self.boundary.apply_into(x, &mut self.cycle_image);
                if self.cycle_image.iter().any(|&word| word != 0) {
                    return Err(PyValueError::new_err(
                        "class queries require a cycle (Az=0)",
                    ));
                }
            }
            if pairs
                .iter()
                .any(|&(i, j)| i >= vectors.len() || j >= vectors.len())
            {
                return Err(PyValueError::new_err(
                    "pairs must index two cycles in this batch",
                ));
            }
            let words = self.n.div_ceil(64);
            checkpoint(0, None, started, wall, &cancellation)?;
            let size = words
                .checked_mul(vectors.len())
                .ok_or_else(|| PyMemoryError::new_err("geometry workspace size overflow"))?;
            self.projected.clear();
            if size > self.projected.capacity() {
                self.projected
                    .try_reserve_exact(size)
                    .map_err(|_| PyMemoryError::new_err("geometry workspace allocation failed"))?;
                self.buffer_growths += 1;
            }
            let mut supports = Vec::with_capacity(vectors.len());
            let mut masses = Vec::with_capacity(vectors.len());
            let mut representatives = Vec::with_capacity(vectors.len());
            for (used, x) in vectors.iter().enumerate() {
                checkpoint(used, state_limit, started, wall, &cancellation)?;
                match self.form.as_str() {
                    "Matrix" => self.factors[0].apply_into(x, &mut self.projected_one),
                    "HC" => {
                        self.factors[1].apply_into(x, &mut self.coefficients);
                        self.factors[0].apply_into(&self.coefficients, &mut self.projected_one);
                    }
                    _ => {
                        self.factors[0].apply_into(x, &mut self.a_image);
                        self.factors[2].apply_into(&self.a_image, &mut self.coefficients);
                        self.retracted.copy_from_slice(x);
                        for (i, &pivot) in self.pivots[0].iter().enumerate() {
                            self.retracted[pivot / 64] ^=
                                ((self.coefficients[i / 64] >> (i % 64)) & 1) << (pivot % 64);
                        }
                        self.factors[3].apply_into(&self.retracted, &mut self.coefficients);
                        self.boundary_coefficients.fill(0);
                        for (i, &pivot) in self.pivots[1].iter().enumerate() {
                            self.boundary_coefficients[pivot / 64] |=
                                ((self.coefficients[i / 64] >> (i % 64)) & 1) << (pivot % 64);
                        }
                        self.factors[1]
                            .apply_into(&self.boundary_coefficients, &mut self.projected_one);
                        for (z, r) in self.projected_one.iter_mut().zip(&self.retracted) {
                            *z ^= r;
                        }
                    }
                }
                if self.complement {
                    for (z, bit) in self.projected_one.iter_mut().zip(x) {
                        *z ^= bit;
                    }
                }
                let indices = support(&self.projected_one);
                masses.push(checked_mass(&self.weights, &indices));
                supports.push(indices);
                self.projected.extend_from_slice(&self.projected_one);
                representatives.push(self.projected_one.clone());
            }
            let mut distances = Vec::with_capacity(pairs.len());
            let mut difference_supports = Vec::with_capacity(pairs.len());
            let mut shared = Vec::with_capacity(pairs.len());
            let mut union = Vec::with_capacity(pairs.len());
            for (used, (i, j)) in pairs.into_iter().enumerate() {
                checkpoint(
                    vectors.len() + used,
                    state_limit,
                    started,
                    wall,
                    &cancellation,
                )?;
                let left = &self.projected[i * words..(i + 1) * words];
                let right = &self.projected[j * words..(j + 1) * words];
                for (out, (&a, &b)) in self.retracted.iter_mut().zip(left.iter().zip(right)) {
                    *out = a ^ b;
                }
                let indices = support(&self.retracted);
                distances.push(checked_mass(&self.weights, &indices));
                difference_supports.push(indices);
                for (out, (&a, &b)) in self.retracted.iter_mut().zip(left.iter().zip(right)) {
                    *out = a & b;
                }
                shared.push(support(&self.retracted));
                for (out, (&a, &b)) in self.retracted.iter_mut().zip(left.iter().zip(right)) {
                    *out = a | b;
                }
                union.push(support(&self.retracted));
            }
            self.batches += 1;
            Ok((
                representatives,
                supports,
                masses,
                distances,
                difference_supports,
                shared,
                union,
                started.elapsed().as_secs_f64(),
            ))
        })
    }
}

fn inverse_action(
    rows: &Packed,
    indices: &[usize],
    size: usize,
    vector: &[u64],
) -> PyResult<Vec<u64>> {
    let coefficients = rows.apply(vector)?;
    let mut output = zeros(size.div_ceil(64))?;
    for (i, &pivot) in indices.iter().enumerate() {
        output[pivot / 64] |= ((coefficients[i / 64] >> (i % 64)) & 1) << (pivot % 64);
    }
    Ok(output)
}

#[pyfunction]
pub fn compact_actions(
    form: &str,
    rows: Vec<Vec<Vec<u64>>>,
    columns: Vec<usize>,
    pivots: Vec<Vec<usize>>,
    complement: bool,
    vectors: Vec<Vec<u64>>,
) -> PyResult<CompactBatch> {
    if rows.len() != columns.len() {
        return Err(PyValueError::new_err("compact factor shapes differ"));
    }
    let factors = rows
        .into_iter()
        .zip(columns)
        .map(|(r, n)| Packed::new(r, n))
        .collect::<PyResult<Vec<_>>>()?;
    let n = match form {
        "GeneralizedInverse" if factors.len() == 4 && pivots.len() == 2 => {
            let (a, d, g, u) = (&factors[0], &factors[1], &factors[2], &factors[3]);
            if a.n != d.m
                || g.m != pivots[0].len()
                || g.n != a.m
                || u.m != pivots[1].len()
                || u.n != d.m
            {
                return Err(PyValueError::new_err("compact inverse shapes differ"));
            }
            for (indices, limit) in pivots.iter().zip([a.n, d.n]) {
                if indices.iter().any(|&i| i >= limit)
                    || indices.windows(2).any(|pair| pair[0] >= pair[1])
                {
                    return Err(PyValueError::new_err(
                        "compact inverse pivot coordinates invalid",
                    ));
                }
            }
            a.n
        }
        "HC" if factors.len() == 2 && pivots.is_empty() => {
            if factors[0].m != factors[1].n || factors[0].n != factors[1].m {
                return Err(PyValueError::new_err("HC shapes differ"));
            }
            factors[0].m
        }
        _ => return Err(PyValueError::new_err("unsupported compact action form")),
    };
    let started = Instant::now();
    let mut projected = Vec::with_capacity(vectors.len());
    let mut applied = Vec::with_capacity(vectors.len());
    let mut supports = Vec::with_capacity(vectors.len());
    for x in vectors {
        checked_vector(&x, n)?;
        let mut z = if form == "GeneralizedInverse" {
            let ga = inverse_action(&factors[2], &pivots[0], n, &factors[0].apply(&x)?)?;
            let r: Vec<u64> = x.iter().zip(ga).map(|(a, b)| a ^ b).collect();
            let u = inverse_action(&factors[3], &pivots[1], factors[1].n, &r)?;
            r.iter()
                .zip(factors[1].apply(&u)?)
                .map(|(a, b)| a ^ b)
                .collect::<Vec<u64>>()
        } else {
            factors[0].apply(&factors[1].apply(&x)?)?
        };
        if complement {
            for (a, b) in z.iter_mut().zip(&x) {
                *a ^= b;
            }
        }
        supports.push((0..n).filter(|&i| z[i / 64] >> (i % 64) & 1 != 0).collect());
        applied.push(x.iter().zip(&z).map(|(a, b)| a ^ b).collect());
        projected.push(z);
    }
    Ok((
        projected,
        applied,
        supports,
        started.elapsed().as_secs_f64(),
    ))
}

// Finite solver kernels. Enumeration order matches itertools.product((0,1), ...).
// u128 ratios are compared by Euclidean division, never overflowing cross-products.
fn ratio_greater(mut a: u128, mut b: u128, mut c: u128, mut d: u128) -> bool {
    let mut reversed = false;
    loop {
        let (q, r, s, t) = (a / b, a % b, c / d, c % d);
        if q != s {
            return if reversed { q < s } else { q > s };
        }
        if r == 0 || t == 0 {
            return if reversed {
                r == 0 && t != 0
            } else {
                r != 0 && t == 0
            };
        }
        (a, b, c, d) = (b, r, d, t);
        reversed = !reversed;
    }
}

fn span_count(basis: &[Vec<u64>], n: usize, weights: &[u128]) -> PyResult<usize> {
    if basis.len() > 16 || weights.len() != n || weights.contains(&0) {
        return Err(PyValueError::new_err(
            "finite span or positive weight shape invalid",
        ));
    }
    weights
        .iter()
        .try_fold(0_u128, |a, b| a.checked_add(*b))
        .ok_or_else(|| PyValueError::new_err("exact weight sum exceeds u128"))?;
    for z in basis {
        checked_vector(z, n)?;
    }
    Ok((1_usize << basis.len()) - 1)
}

fn mass(z: &[u64], weights: &[u128]) -> u128 {
    z.iter()
        .enumerate()
        .map(|(word, &bits)| {
            let mut bits = bits;
            let mut value = 0;
            while bits != 0 {
                value += weights[word * 64 + bits.trailing_zeros() as usize];
                bits &= bits - 1;
            }
            value
        })
        .sum()
}

fn span_step(z: &mut [u64], basis: &[Vec<u64>], previous: usize, current: usize) {
    let mut changed = previous ^ current;
    while changed != 0 {
        let i = basis.len() - 1 - changed.trailing_zeros() as usize;
        for (a, b) in z.iter_mut().zip(&basis[i]) {
            *a ^= b;
        }
        changed &= changed - 1;
    }
}

fn stopped(
    used: usize,
    quota: usize,
    started: std::time::Instant,
    wall: Option<f64>,
    cancellation: &Option<std::sync::Arc<std::sync::atomic::AtomicBool>>,
) -> Option<String> {
    if cancellation
        .as_ref()
        .is_some_and(|flag| flag.load(std::sync::atomic::Ordering::Relaxed))
    {
        Some("cancelled".to_owned())
    } else if used >= quota {
        Some("state_limit".to_owned())
    } else if wall.is_some_and(|w| started.elapsed().as_secs_f64() >= w) {
        Some("wall_time_limit".to_owned())
    } else {
        None
    }
}

pub(super) fn checkpoint(
    used: usize,
    quota: Option<usize>,
    started: std::time::Instant,
    wall: Option<f64>,
    cancellation: &Option<std::sync::Arc<std::sync::atomic::AtomicBool>>,
) -> PyResult<()> {
    if let Some(reason) = stopped(
        used,
        quota.unwrap_or(usize::MAX),
        started,
        wall,
        cancellation,
    ) {
        return Err(PyValueError::new_err(format!(
            "resource_exhausted:{reason}:{used}"
        )));
    }
    Ok(())
}

fn check_wall(wall: Option<f64>) -> PyResult<()> {
    if wall.is_some_and(|w| !w.is_finite() || w < 0.0) {
        Err(PyValueError::new_err(
            "wall limit must be finite and nonnegative",
        ))
    } else {
        Ok(())
    }
}

type SpanObjective = (u128, u128, Option<Vec<u64>>, usize, Option<String>);
#[pyfunction]
#[pyo3(signature=(basis, images, weights, quota, wall, cancellation=None))]
#[allow(clippy::too_many_arguments)]
pub fn span_objective(
    py: Python<'_>,
    basis: Vec<Vec<u64>>,
    images: Vec<Vec<u64>>,
    weights: Vec<u128>,
    quota: usize,
    wall: Option<f64>,
    cancellation: Option<PyRef<'_, super::CancellationFlag>>,
) -> PyResult<SpanObjective> {
    let n = weights.len();
    let count = span_count(&basis, n, &weights)?;
    check_wall(wall)?;
    if images.len() != basis.len() {
        return Err(PyValueError::new_err("span images differ"));
    }
    for y in &images {
        checked_vector(y, n)?;
    }
    let cancellation = cancellation.map(|flag| flag.state.clone());
    py.detach(move || {
        let started = std::time::Instant::now();
        let mut z = zeros(n.div_ceil(64))?;
        let mut y = z.clone();
        let (mut num, mut den, mut witness) = (0, 1, None);
        for i in 1..=count {
            if let Some(reason) = stopped(i - 1, quota, started, wall, &cancellation) {
                return Ok((num, den, witness, i - 1, Some(reason)));
            }
            span_step(&mut z, &basis, i - 1, i);
            span_step(&mut y, &images, i - 1, i);
            let (a, b) = (mass(&y, &weights), mass(&z, &weights));
            if b == 0 {
                return Err(PyValueError::new_err("cycle basis must be independent"));
            }
            if witness.is_none() || ratio_greater(a, b, num, den) {
                (num, den, witness) = (a, b, Some(z.clone()));
            }
        }
        Ok((num, den, witness, count, None))
    })
}

type SpanTable = (Vec<Vec<u64>>, Vec<u128>, usize, Option<String>);
#[pyfunction]
#[pyo3(signature=(basis, weights, quota, wall, cancellation=None))]
pub fn span_table(
    py: Python<'_>,
    basis: Vec<Vec<u64>>,
    weights: Vec<u128>,
    quota: usize,
    wall: Option<f64>,
    cancellation: Option<PyRef<'_, super::CancellationFlag>>,
) -> PyResult<SpanTable> {
    let n = weights.len();
    let count = span_count(&basis, n, &weights)?;
    check_wall(wall)?;
    let cancellation = cancellation.map(|flag| flag.state.clone());
    py.detach(move || {
        let started = std::time::Instant::now();
        let mut z = zeros(n.div_ceil(64))?;
        let (mut vectors, mut masses) = (
            Vec::with_capacity(count.min(quota)),
            Vec::with_capacity(count.min(quota)),
        );
        for i in 1..=count {
            if let Some(reason) = stopped(i - 1, quota, started, wall, &cancellation) {
                return Ok((vectors, masses, i - 1, Some(reason)));
            }
            span_step(&mut z, &basis, i - 1, i);
            if !z.iter().any(|&x| x != 0) {
                return Err(PyValueError::new_err("cycle basis must be independent"));
            }
            masses.push(mass(&z, &weights));
            vectors.push(z.clone());
        }
        Ok((vectors, masses, count, None))
    })
}

#[pyfunction]
pub fn packed_apply(
    rows: Vec<Vec<u64>>,
    n: usize,
    vectors: Vec<Vec<u64>>,
) -> PyResult<Vec<Vec<u64>>> {
    let matrix = Packed::new(rows, n)?;
    vectors.iter().map(|z| matrix.apply(z)).collect()
}

#[pyfunction]
pub fn cyclic_batch(m: usize, vectors: Vec<Vec<u64>>) -> PyResult<Vec<Vec<u64>>> {
    if !(2..=4).contains(&m) {
        return Err(PyValueError::new_err("cyclic supports m=2,3,4"));
    }
    let n = (1_usize << m) - 1;
    let mask = (1_u64 << n) - 1;
    vectors
        .iter()
        .map(|z| {
            checked_vector(z, n)?;
            let x = z[0];
            let y = (0..m).fold(0, |a, i| {
                let shift = 1 << i;
                a ^ (((x << shift) & mask) | (x >> (n - shift)))
            });
            Ok(vec![y])
        })
        .collect()
}

#[cfg(test)]
mod solver_tests {
    use super::ratio_greater;
    #[test]
    fn exact_fraction_order_without_cross_product_overflow() {
        for a in 0..20 {
            for b in 1..20 {
                for c in 0..20 {
                    for d in 1..20 {
                        assert_eq!(ratio_greater(a, b, c, d), a * d > c * b);
                    }
                }
            }
        }
        assert!(ratio_greater(
            u128::MAX,
            u128::MAX - 1,
            u128::MAX - 1,
            u128::MAX
        ));
        assert!(!ratio_greater(
            u128::MAX,
            u128::MAX,
            u128::MAX - 1,
            u128::MAX - 1
        ));
    }
}

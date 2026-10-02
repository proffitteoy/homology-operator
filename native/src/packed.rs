//! General multiword F2 rows. Stable pivots never permute original coordinates.
use pyo3::exceptions::{PyMemoryError, PyValueError};
use pyo3::prelude::*;

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
        for i in 0..self.m {
            let parity = self
                .row(i)
                .iter()
                .zip(x)
                .fold(0, |p, (a, b)| p ^ ((a & b).count_ones() & 1));
            output[i / 64] |= u64::from(parity) << (i % 64);
        }
        Ok(output)
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
    fn new(rows: Vec<Vec<u64>>, ncols: usize) -> PyResult<Self> {
        let original = Packed::new(rows, ncols)?;
        let mut reduced = original.clone();
        let mut transform = Packed::zero(original.m, original.m)?;
        for i in 0..original.m {
            transform.set(i, i);
        }
        let mut pivots = Vec::new();
        let mut nnz = reduced.nnz();
        let mut peak_nnz = nnz;
        for col in 0..original.n {
            let pivot_row = pivots.len();
            if let Some(selected) = (pivot_row..original.m).find(|&row| reduced.bit(row, col)) {
                reduced.swap(pivot_row, selected);
                transform.swap(pivot_row, selected);
                for row in 0..original.m {
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
) -> Option<String> {
    if used >= quota {
        Some("state_limit".to_owned())
    } else if wall.is_some_and(|w| started.elapsed().as_secs_f64() >= w) {
        Some("wall_time_limit".to_owned())
    } else {
        None
    }
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
pub fn span_objective(
    basis: Vec<Vec<u64>>,
    images: Vec<Vec<u64>>,
    weights: Vec<u128>,
    quota: usize,
    wall: Option<f64>,
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
    let started = std::time::Instant::now();
    let mut z = zeros(n.div_ceil(64))?;
    let mut y = z.clone();
    let (mut num, mut den, mut witness) = (0, 1, None);
    for i in 1..=count {
        if let Some(reason) = stopped(i - 1, quota, started, wall) {
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
}

type SpanTable = (Vec<Vec<u64>>, Vec<u128>, usize, Option<String>);
#[pyfunction]
pub fn span_table(
    basis: Vec<Vec<u64>>,
    weights: Vec<u128>,
    quota: usize,
    wall: Option<f64>,
) -> PyResult<SpanTable> {
    let n = weights.len();
    let count = span_count(&basis, n, &weights)?;
    check_wall(wall)?;
    let started = std::time::Instant::now();
    let mut z = zeros(n.div_ceil(64))?;
    let (mut vectors, mut masses) = (
        Vec::with_capacity(count.min(quota)),
        Vec::with_capacity(count.min(quota)),
    );
    for i in 1..=count {
        if let Some(reason) = stopped(i - 1, quota, started, wall) {
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

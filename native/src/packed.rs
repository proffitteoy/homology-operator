//! General multiword F2 rows. Stable pivots never permute original coordinates.
use pyo3::exceptions::{PyMemoryError, PyValueError};
use pyo3::prelude::*;
use std::borrow::Cow;
use std::sync::{Arc, atomic::AtomicBool};
use std::time::Instant;

#[derive(Clone)]
struct Packed {
    m: usize,
    n: usize,
    words: usize,
    data: Vec<u64>,
    // Sorted nonzero column indices. Sparse elimination densifies once actual
    // fill makes index storage larger than half the packed allocation.
    sparse: Option<Vec<Vec<usize>>>,
    sparse_nnz: usize,
    densifications: usize,
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
    fn identity(n: usize) -> PyResult<Self> {
        let mut matrix = Self::zero(n, n)?;
        for i in 0..n {
            matrix.set(i, i);
        }
        Ok(matrix)
    }

    fn product(&self, other: &Self) -> PyResult<Self> {
        if self.n != other.m {
            return Err(PyValueError::new_err("product inner dimensions differ"));
        }
        let mut output = Self::zero(self.m, other.n)?;
        for i in 0..self.m {
            let mut row = zeros(other.words)?;
            for j in self.indices(i) {
                other.xor_into(j, &mut row);
            }
            output.replace_row(i, &row);
        }
        Ok(output)
    }
    fn zero(m: usize, n: usize) -> PyResult<Self> {
        let words = n.div_ceil(64);
        let size = m
            .checked_mul(words)
            .ok_or_else(|| PyMemoryError::new_err("packed size overflow"))?;
        Ok(Self {
            m,
            n,
            words,
            data: if words >= 8 { vec![] } else { zeros(size)? },
            sparse: (words >= 8).then(|| vec![vec![]; m]),
            sparse_nnz: 0,
            densifications: 0,
        })
    }

    fn new(rows: Vec<Vec<u64>>, n: usize) -> PyResult<Self> {
        for row in &rows {
            checked_vector(row, n)?;
        }
        let mut matrix = Self::zero(rows.len(), n)?;
        for (i, row) in rows.iter().enumerate() {
            matrix.replace_row(i, row);
        }
        Ok(matrix)
    }

    fn row(&self, i: usize) -> Cow<'_, [u64]> {
        if let Some(rows) = &self.sparse {
            let mut output = vec![0; self.words];
            for &j in &rows[i] {
                output[j / 64] |= 1 << (j % 64);
            }
            Cow::Owned(output)
        } else {
            Cow::Borrowed(&self.data[i * self.words..(i + 1) * self.words])
        }
    }
    fn indices(&self, i: usize) -> Vec<usize> {
        if let Some(rows) = &self.sparse {
            return rows[i].clone();
        }
        let mut output = Vec::new();
        for (word, &bits) in self.row(i).iter().enumerate() {
            let mut bits = bits;
            while bits != 0 {
                output.push(word * 64 + bits.trailing_zeros() as usize);
                bits &= bits - 1;
            }
        }
        output
    }
    fn densify_if_needed(&mut self) {
        if self.sparse.is_some() && self.sparse_nnz > self.m * self.words / 2 {
            self.data = vec![0; self.m * self.words];
            for (i, row) in self.sparse.take().unwrap().iter().enumerate() {
                for &j in row {
                    self.data[i * self.words + j / 64] |= 1 << (j % 64);
                }
            }
            self.densifications += 1;
        }
    }
    fn replace_row(&mut self, i: usize, row: &[u64]) {
        if let Some(rows) = &mut self.sparse {
            self.sparse_nnz -= rows[i].len();
            rows[i].clear();
            for (word, &bits) in row.iter().enumerate() {
                let mut bits = bits;
                while bits != 0 {
                    rows[i].push(word * 64 + bits.trailing_zeros() as usize);
                    bits &= bits - 1;
                }
            }
            self.sparse_nnz += rows[i].len();
            self.densify_if_needed();
        } else {
            self.data[i * self.words..(i + 1) * self.words].copy_from_slice(row);
        }
    }
    fn xor_into(&self, i: usize, output: &mut [u64]) {
        if let Some(rows) = &self.sparse {
            for &j in &rows[i] {
                output[j / 64] ^= 1 << (j % 64);
            }
        } else {
            for (x, y) in output.iter_mut().zip(self.row(i).iter()) {
                *x ^= y;
            }
        }
    }
    fn add(&self, other: &Self) -> PyResult<Self> {
        if (self.m, self.n) != (other.m, other.n) {
            return Err(PyValueError::new_err("addition requires equal shapes"));
        }
        let mut output = self.clone();
        for i in 0..self.m {
            let mut row = output.row(i).to_vec();
            other.xor_into(i, &mut row);
            output.replace_row(i, &row);
        }
        Ok(output)
    }
    fn transpose(&self) -> PyResult<Self> {
        let mut output = Self::zero(self.n, self.m)?;
        for i in 0..self.m {
            for j in self.indices(i) {
                output.set(j, i);
            }
        }
        Ok(output)
    }
    fn stored_words(&self) -> usize {
        self.sparse
            .as_ref()
            .map_or(self.data.len(), |r| r.iter().map(Vec::len).sum())
    }
    fn rows(&self) -> Vec<Vec<u64>> {
        (0..self.m).map(|i| self.row(i).to_vec()).collect()
    }
    fn bit(&self, i: usize, j: usize) -> bool {
        self.sparse.as_ref().map_or_else(
            || self.data[i * self.words + j / 64] >> (j % 64) & 1 != 0,
            |rows| rows[i].binary_search(&j).is_ok(),
        )
    }
    fn set(&mut self, i: usize, j: usize) {
        if let Some(rows) = &mut self.sparse {
            if let Err(at) = rows[i].binary_search(&j) {
                rows[i].insert(at, j);
                self.sparse_nnz += 1;
                self.densify_if_needed();
            }
        } else {
            self.data[i * self.words + j / 64] |= 1_u64 << (j % 64);
        }
    }
    fn nnz(&self) -> usize {
        if self.sparse.is_some() {
            return self.sparse_nnz;
        }
        self.data
            .iter()
            .map(|word| word.count_ones() as usize)
            .sum()
    }
    fn swap(&mut self, i: usize, j: usize) {
        if let Some(rows) = &mut self.sparse {
            rows.swap(i, j);
            return;
        }
        for word in 0..self.words {
            self.data.swap(i * self.words + word, j * self.words + word);
        }
    }
    fn xor_row(&mut self, i: usize, j: usize) {
        if let Some(rows) = &mut self.sparse {
            let (a, b) = (&rows[i], &rows[j]);
            let mut merged = Vec::with_capacity(a.len() + b.len());
            let (mut x, mut y) = (0, 0);
            while x < a.len() || y < b.len() {
                if y == b.len() || (x < a.len() && a[x] < b[y]) {
                    merged.push(a[x]);
                    x += 1;
                } else if x == a.len() || b[y] < a[x] {
                    merged.push(b[y]);
                    y += 1;
                } else {
                    x += 1;
                    y += 1;
                }
            }
            self.sparse_nnz = self.sparse_nnz - rows[i].len() + merged.len();
            rows[i] = merged;
            self.densify_if_needed();
            return;
        }
        for word in 0..self.words {
            self.data[i * self.words + word] ^= self.data[j * self.words + word];
        }
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
            let parity = if let Some(rows) = &self.sparse {
                rows[i]
                    .iter()
                    .fold(0, |p, &j| p ^ ((x[j / 64] >> (j % 64)) & 1) as u32)
            } else {
                self.row(i)
                    .iter()
                    .zip(x)
                    .fold(0, |p, (a, b)| p ^ ((a & b).count_ones() & 1))
            };
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
    let b = Packed::new(b, bn)?;
    if a.m != b.m || a.n != b.n {
        return Err(PyValueError::new_err("addition requires equal shapes"));
    }
    Ok(a.add(&b)?.rows())
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
    Ok(a.product(&b)?.rows())
}

/// Immutable process-local matrix. Algebra returns handles; coordinates are
/// exported only at the public/reference-validation or serialization boundary.
#[pyclass(frozen, skip_from_py_object)]
#[derive(Clone)]
pub struct NativeMatrix {
    inner: Arc<Packed>,
}

#[pymethods]
impl NativeMatrix {
    #[new]
    fn new(rows: Vec<Vec<u64>>, ncols: usize) -> PyResult<Self> {
        Ok(Self {
            inner: Arc::new(Packed::new(rows, ncols)?),
        })
    }
    #[staticmethod]
    fn from_sparse_rows(rows: Vec<Vec<usize>>, ncols: usize) -> PyResult<Self> {
        let mut matrix = Packed::zero(rows.len(), ncols)?;
        for (i, row) in rows.iter().enumerate() {
            if row.iter().any(|&j| j >= ncols) || row.windows(2).any(|p| p[0] >= p[1]) {
                return Err(PyValueError::new_err(
                    "sparse indices must be ordered, unique and in range",
                ));
            }
            for &j in row {
                matrix.set(i, j);
            }
        }
        Ok(Self {
            inner: Arc::new(matrix),
        })
    }
    #[getter]
    fn nrows(&self) -> usize {
        self.inner.m
    }
    #[getter]
    fn ncols(&self) -> usize {
        self.inner.n
    }
    fn rows(&self) -> Vec<Vec<u64>> {
        self.inner.rows()
    }
    fn transpose(&self, py: Python<'_>) -> PyResult<Self> {
        py.detach(|| {
            Ok(Self {
                inner: Arc::new(self.inner.transpose()?),
            })
        })
    }
    fn add(&self, py: Python<'_>, other: PyRef<'_, Self>) -> PyResult<Self> {
        let other = other.inner.clone();
        py.detach(|| {
            Ok(Self {
                inner: Arc::new(self.inner.add(&other)?),
            })
        })
    }
    fn product(&self, py: Python<'_>, other: PyRef<'_, Self>) -> PyResult<Self> {
        let other = other.inner.clone();
        py.detach(|| {
            Ok(Self {
                inner: Arc::new(self.inner.product(&other)?),
            })
        })
    }
    fn apply_many(&self, py: Python<'_>, vectors: Vec<Vec<u64>>) -> PyResult<Vec<Vec<u64>>> {
        py.detach(|| vectors.iter().map(|v| self.inner.apply(v)).collect())
    }
    fn storage(&self) -> (bool, usize, usize) {
        (
            self.inner.sparse.is_some(),
            self.inner.stored_words(),
            self.inner.densifications,
        )
    }
}

#[pyclass(frozen)]
pub struct PreparedMatrix {
    original: Packed,
    reduced: Packed,
    transform: Option<Packed>,
    pivots: Vec<usize>,
    peak_nnz: Option<usize>,
}

impl PreparedMatrix {
    fn prepare(
        original: Packed,
        full: bool,
        diagnostics: bool,
        cancellation: &Option<Arc<AtomicBool>>,
    ) -> PyResult<Self> {
        let started = Instant::now();
        checkpoint(0, None, started, None, cancellation)?;
        let mut reduced = original.clone();
        let mut transform = if full {
            Some(Packed::zero(original.m, original.m)?)
        } else {
            None
        };
        if let Some(e) = &mut transform {
            for i in 0..original.m {
                e.set(i, i);
            }
        }
        let mut pivots = Vec::new();
        let mut nnz = if diagnostics { reduced.nnz() } else { 0 };
        let mut peak_nnz = diagnostics.then_some(nnz);
        for col in 0..original.n {
            checkpoint(0, None, started, None, cancellation)?;
            let pivot_row = pivots.len();
            if let Some(selected) = (pivot_row..original.m).find(|&row| reduced.bit(row, col)) {
                reduced.swap(pivot_row, selected);
                if let Some(e) = &mut transform {
                    e.swap(pivot_row, selected);
                }
                for row in 0..original.m {
                    checkpoint(0, None, started, None, cancellation)?;
                    if row != pivot_row && reduced.bit(row, col) {
                        let before = if diagnostics {
                            reduced
                                .row(row)
                                .iter()
                                .map(|x| x.count_ones() as usize)
                                .sum()
                        } else {
                            0
                        };
                        reduced.xor_row(row, pivot_row);
                        if let Some(peak) = &mut peak_nnz {
                            let after: usize = reduced
                                .row(row)
                                .iter()
                                .map(|x| x.count_ones() as usize)
                                .sum();
                            nnz = nnz - before + after;
                            *peak = (*peak).max(nnz);
                        }
                        if let Some(e) = &mut transform {
                            e.xor_row(row, pivot_row);
                        }
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

    fn row_transform(&self) -> PyResult<&Packed> {
        self.transform.as_ref().ok_or_else(|| {
            PyValueError::new_err(
                "full=False decomposition does not support solves or inverse rows",
            )
        })
    }
}

#[pymethods]
impl PreparedMatrix {
    #[new]
    #[pyo3(signature=(rows, ncols, cancellation=None, full=true, diagnostics=true))]
    fn new(
        py: Python<'_>,
        rows: Vec<Vec<u64>>,
        ncols: usize,
        cancellation: Option<PyRef<'_, super::CancellationFlag>>,
        full: bool,
        diagnostics: bool,
    ) -> PyResult<Self> {
        let cancellation = cancellation.map(|flag| flag.state.clone());
        py.detach(move || {
            Self::prepare(Packed::new(rows, ncols)?, full, diagnostics, &cancellation)
        })
    }

    #[staticmethod]
    #[pyo3(signature=(matrix, cancellation=None, full=true, diagnostics=true))]
    fn from_matrix(
        py: Python<'_>,
        matrix: PyRef<'_, NativeMatrix>,
        cancellation: Option<PyRef<'_, super::CancellationFlag>>,
        full: bool,
        diagnostics: bool,
    ) -> PyResult<Self> {
        let original = matrix.inner.clone();
        let cancellation = cancellation.map(|f| f.state.clone());
        py.detach(move || Self::prepare((*original).clone(), full, diagnostics, &cancellation))
    }
    fn reduced_matrix(&self) -> NativeMatrix {
        NativeMatrix {
            inner: Arc::new(self.reduced.clone()),
        }
    }
    fn inverse_matrix(&self) -> PyResult<NativeMatrix> {
        Ok(NativeMatrix {
            inner: Arc::new(Packed::new(self.inverse_rows()?, self.original.m)?),
        })
    }
    fn kernel_matrix(&self) -> PyResult<NativeMatrix> {
        Ok(NativeMatrix {
            inner: Arc::new(Packed::new(self.kernel_basis()?, self.original.n)?.transpose()?),
        })
    }
    fn image_matrix(&self) -> PyResult<NativeMatrix> {
        Ok(NativeMatrix {
            inner: Arc::new(Packed::new(self.image_basis()?, self.original.m)?.transpose()?),
        })
    }
    fn solve_matrix(&self, other: PyRef<'_, NativeMatrix>) -> PyResult<NativeMatrix> {
        if other.inner.m != self.original.m {
            return Err(PyValueError::new_err("solve shape differs"));
        }
        let columns = other.inner.transpose()?.rows();
        let solutions = self
            .solve_many(columns)?
            .into_iter()
            .map(|s| s.ok_or_else(|| PyValueError::new_err("inconsistent matrix solve")))
            .collect::<PyResult<Vec<_>>>()?;
        Ok(NativeMatrix {
            inner: Arc::new(Packed::new(solutions, self.original.n)?.transpose()?),
        })
    }
    fn storage(&self) -> (bool, bool, usize) {
        (
            self.original.sparse.is_some(),
            self.reduced.sparse.is_some(),
            self.reduced.densifications,
        )
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
    fn peak_nonzero_bits(&self) -> Option<usize> {
        self.peak_nnz
    }
    #[getter]
    fn stored_words(&self) -> usize {
        self.original.stored_words()
            + self.reduced.stored_words()
            + self.transform.as_ref().map_or(0, Packed::stored_words)
    }

    fn rank(&self) -> usize {
        self.pivots.len()
    }

    fn inverse_rows(&self) -> PyResult<Vec<Vec<u64>>> {
        // Continue the reference RREF through the RIGHT side of [M | I].
        // Its null coefficient rows can change the upper inverse rows.
        let mut transform = self.row_transform()?.clone();
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
            let y = self.row_transform()?.apply(&x)?;
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
            let y = self.row_transform()?.apply(&x)?;
            output.push(
                !(self.pivots.len()..self.original.m).any(|i| y[i / 64] >> (i % 64) & 1 != 0),
            );
        }
        Ok(output)
    }
}

type CompactBatch = (Vec<Vec<u64>>, Vec<Vec<u64>>, Vec<Vec<usize>>, f64);

type HCFactors = (NativeMatrix, NativeMatrix);

type MultiConstruction = (
    Option<NativeMatrix>,
    Option<NativeMatrix>,
    Option<NativeMatrix>,
    usize,
    f64,
    Option<String>,
);

#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature=(a, n, d, p, state_limit, wall_limit, entry_limit, cancellation=None))]
pub fn construct_multi(
    py: Python<'_>,
    a: PyRef<'_, NativeMatrix>,
    n: usize,
    d: PyRef<'_, NativeMatrix>,
    p: usize,
    state_limit: usize,
    wall_limit: f64,
    entry_limit: usize,
    cancellation: Option<PyRef<'_, super::CancellationFlag>>,
) -> PyResult<MultiConstruction> {
    check_wall(Some(wall_limit))?;
    let a = (*a.inner).clone();
    let d = (*d.inner).clone();
    if a.n != n || d.m != n || d.n != p {
        return Err(PyValueError::new_err("chain dimensions differ"));
    }
    if a.product(&d)?.nnz() != 0 {
        return Err(PyValueError::new_err("AD must be zero"));
    }
    let cancellation = cancellation.map(|flag| flag.state.clone());
    py.detach(move || {
        let mut budget = super::Budget {
            cancellation: cancellation.clone(),
            started: Instant::now(),
            states: 0,
            state_limit,
            wall_limit,
            entry_limit,
        };
        // Check the same logical dense-entry bound, with overflow rejection.
        let entries = [
            (a.m, n),
            (n, p),
            (n, a.m),
            (p, n),
            (n, n),
            (n, n),
            (n, n),
            (n, n),
        ]
        .into_iter()
        .try_fold(0_usize, |sum, (x, y)| sum.checked_add(x.checked_mul(y)?));
        let stop = |reason: &str| PyValueError::new_err(format!("resource_exhausted:{reason}:0"));
        let result = (|| {
            budget.step().map_err(stop)?;
            budget
                .entries(entries.ok_or_else(|| stop("matrix_entry_limit"))?)
                .map_err(stop)?;
            let mut inverses = Vec::new();
            for matrix in [&a, &d] {
                budget.step().map_err(stop)?;
                let inverse_entries = matrix
                    .n
                    .checked_add(matrix.m)
                    .and_then(|width| matrix.m.checked_mul(width));
                budget
                    .entries(inverse_entries.ok_or_else(|| stop("matrix_entry_limit"))?)
                    .map_err(stop)?;
                let prepared = PreparedMatrix::prepare(matrix.clone(), true, false, &cancellation)?;
                let inverse_rows = prepared.inverse_rows()?;
                let mut inverse = Packed::zero(matrix.n, matrix.m)?;
                for (row, &pivot) in prepared.pivots.iter().enumerate() {
                    inverse.replace_row(pivot, &inverse_rows[row]);
                }
                for _ in 0..matrix.m {
                    budget.step().map_err(stop)?;
                }
                inverses.push(inverse);
            }
            budget.step().map_err(stop)?;
            let identity = Packed::identity(n)?;
            let r = identity.add(&inverses[0].product(&a)?)?;
            let q = identity.add(&d.product(&inverses[1])?)?;
            let projection = q.product(&r)?;
            budget.step().map_err(stop)?;
            Ok::<_, PyErr>((
                NativeMatrix {
                    inner: Arc::new(inverses.remove(0)),
                },
                NativeMatrix {
                    inner: Arc::new(inverses.remove(0)),
                },
                NativeMatrix {
                    inner: Arc::new(projection),
                },
            ))
        })();
        let wall = budget.started.elapsed().as_secs_f64();
        Ok(match result {
            Ok((g, u, p)) => (Some(g), Some(u), Some(p), budget.states, wall, None),
            Err(error) => {
                let message = error.to_string();
                if let Some(reason) = message
                    .split("resource_exhausted:")
                    .nth(1)
                    .and_then(|s| s.split(':').next())
                {
                    (
                        None,
                        None,
                        None,
                        budget.states,
                        wall,
                        Some(reason.to_owned()),
                    )
                } else {
                    return Err(error);
                }
            }
        })
    })
}

/// Build the stable canonical image H and its coordinate rows C entirely here.
/// Only H/C cross the binding. No n-by-n P or repeated per-column solves.
#[pyfunction]
#[pyo3(signature=(a, d, cancellation=None, wall=None))]
pub fn hc_factors(
    py: Python<'_>,
    a: PyRef<'_, PreparedMatrix>,
    d: PyRef<'_, PreparedMatrix>,
    cancellation: Option<PyRef<'_, super::CancellationFlag>>,
    wall: Option<f64>,
) -> PyResult<HCFactors> {
    check_wall(wall)?;
    if a.original.n != d.original.m {
        return Err(PyValueError::new_err("HC chain dimensions differ"));
    }
    let g = Packed::new(a.inverse_rows()?, a.original.m)?;
    let u = Packed::new(d.inverse_rows()?, d.original.m)?;
    let (a, d, ap, dp) = (
        a.original.clone(),
        d.original.clone(),
        a.pivots.clone(),
        d.pivots.clone(),
    );
    let cancellation = cancellation.map(|flag| flag.state.clone());
    py.detach(move || {
        let started = Instant::now();
        let n = a.n;
        let mut e = zeros(n.div_ceil(64))?;
        let mut ax = zeros(a.m.div_ceil(64))?;
        let mut ga = zeros(ap.len().div_ceil(64))?;
        let mut r = zeros(n.div_ceil(64))?;
        let mut ur = zeros(dp.len().div_ceil(64))?;
        let mut du = zeros(d.n.div_ceil(64))?;
        let mut z = zeros(n.div_ceil(64))?;
        let mut basis: Vec<Option<Vec<u64>>> = vec![None; n];
        for j in 0..n {
            checkpoint(0, None, started, wall, &cancellation)?;
            e.fill(0);
            e[j / 64] = 1 << (j % 64);
            a.apply_into(&e, &mut ax);
            g.apply_into(&ax, &mut ga);
            r.copy_from_slice(&e);
            for (i, &pivot) in ap.iter().enumerate() {
                r[pivot / 64] ^= ((ga[i / 64] >> (i % 64)) & 1) << (pivot % 64);
            }
            u.apply_into(&r, &mut ur);
            du.fill(0);
            for (i, &pivot) in dp.iter().enumerate() {
                du[pivot / 64] |= ((ur[i / 64] >> (i % 64)) & 1) << (pivot % 64);
            }
            d.apply_into(&du, &mut z);
            for (x, y) in z.iter_mut().zip(&r) {
                *x ^= y;
            }
            // Same rightmost reduced span and ordering as CompactAction.
            for pivot in (0..n).rev() {
                if z[pivot / 64] >> (pivot % 64) & 1 != 0
                    && let Some(other) = &basis[pivot]
                {
                    for (x, y) in z.iter_mut().zip(other) {
                        *x ^= y;
                    }
                }
            }
            if let Some(pivot) = (0..n).rev().find(|&i| z[i / 64] >> (i % 64) & 1 != 0) {
                for other in basis.iter_mut().flatten() {
                    if other[pivot / 64] >> (pivot % 64) & 1 != 0 {
                        for (x, y) in other.iter_mut().zip(&z) {
                            *x ^= y;
                        }
                    }
                }
                basis[pivot] = Some(z.clone());
            }
        }
        let beta = basis.iter().flatten().count();
        let mut h = Packed::zero(n, beta)?;
        let mut c = Packed::zero(beta, n)?;
        for (column, (pivot, vector)) in basis
            .iter()
            .enumerate()
            .filter_map(|(i, v)| v.as_ref().map(|v| (i, v)))
            .enumerate()
        {
            checkpoint(0, None, started, wall, &cancellation)?;
            for i in 0..n {
                if vector[i / 64] >> (i % 64) & 1 != 0 {
                    h.set(i, column);
                }
            }
            // H is reduced at these pivot coordinates. Thus C is the selected
            // rows of Q R, computed from factors instead of generating P again.
            let mut q = zeros(n.div_ceil(64))?;
            q[pivot / 64] = 1 << (pivot % 64);
            for (i, &p) in dp.iter().enumerate() {
                if d.bit(pivot, p) {
                    u.xor_into(i, &mut q);
                }
            }
            let mut coefficients = zeros(a.m.div_ceil(64))?;
            for (i, &p) in ap.iter().enumerate() {
                if q[p / 64] >> (p % 64) & 1 != 0 {
                    g.xor_into(i, &mut coefficients);
                }
            }
            for i in 0..a.m {
                if coefficients[i / 64] >> (i % 64) & 1 != 0 {
                    a.xor_into(i, &mut q);
                }
            }
            c.replace_row(column, &q);
        }
        Ok((
            NativeMatrix { inner: Arc::new(h) },
            NativeMatrix { inner: Arc::new(c) },
        ))
    })
}

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

impl GeometryWorkspace {
    fn project_one(&mut self, x: &[u64]) {
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
                self.factors[1].apply_into(&self.boundary_coefficients, &mut self.projected_one);
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
    }
}

#[pymethods]
impl GeometryWorkspace {
    #[new]
    #[allow(clippy::too_many_arguments)]
    fn new(
        py: Python<'_>,
        boundary: PyRef<'_, NativeMatrix>,
        form: String,
        rows: Vec<Py<NativeMatrix>>,
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
            .map(|(r, n)| {
                let matrix = r.borrow(py);
                if matrix.inner.n != n {
                    return Err(PyValueError::new_err("factor shape differs"));
                }
                Ok((*matrix.inner).clone())
            })
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
        if boundary.inner.n != n {
            return Err(PyValueError::new_err("boundary shape differs"));
        }
        let boundary = (*boundary.inner).clone();
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

    fn apply_many(&mut self, py: Python<'_>, vectors: Vec<Vec<u64>>) -> PyResult<CompactBatch> {
        for x in &vectors {
            checked_vector(x, self.n)?;
        }
        py.detach(move || {
            let started = Instant::now();
            let mut projected = Vec::with_capacity(vectors.len());
            let mut applied = Vec::with_capacity(vectors.len());
            let mut supports = Vec::with_capacity(vectors.len());
            for x in vectors {
                self.project_one(&x);
                projected.push(self.projected_one.clone());
                applied.push(
                    x.iter()
                        .zip(&self.projected_one)
                        .map(|(x, p)| x ^ p)
                        .collect(),
                );
                supports.push(support(&self.projected_one));
            }
            Ok((
                projected,
                applied,
                supports,
                started.elapsed().as_secs_f64(),
            ))
        })
    }

    fn statistics(&self) -> (usize, usize, usize) {
        (self.batches, self.buffer_growths, self.projected.capacity())
    }

    fn transport_matrix(
        &mut self,
        py: Python<'_>,
        source: PyRef<'_, NativeMatrix>,
        indices: Vec<usize>,
        target: PyRef<'_, PreparedMatrix>,
    ) -> PyResult<NativeMatrix> {
        if indices.len() != source.inner.m
            || indices.iter().any(|&i| i >= self.n)
            || target.original.m != self.n
        {
            return Err(PyValueError::new_err(
                "transport embedding dimensions differ",
            ));
        }
        let source = source.inner.clone();
        let transform = target.row_transform()?.clone();
        let pivots = target.pivots.clone();
        let coordinate_count = target.original.n;
        py.detach(move || {
            let mut embedded = zeros(self.n.div_ceil(64))?;
            let mut output = Packed::zero(coordinate_count, source.n)?;
            for column in 0..source.n {
                embedded.fill(0);
                for (row, &i) in indices.iter().enumerate() {
                    if source.bit(row, column) {
                        embedded[i / 64] |= 1 << (i % 64);
                    }
                }
                self.project_one(&embedded);
                let y = transform.apply(&self.projected_one)?;
                if (pivots.len()..self.n).any(|i| y[i / 64] >> (i % 64) & 1 != 0) {
                    return Err(PyValueError::new_err(
                        "transport image outside target kernel",
                    ));
                }
                for (row, &pivot) in pivots.iter().enumerate() {
                    if y[row / 64] >> (row % 64) & 1 != 0 {
                        output.set(pivot, column);
                    }
                }
            }
            Ok(NativeMatrix {
                inner: Arc::new(output),
            })
        })
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
                self.project_one(x);
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

type SectionSearch = (
    NativeMatrix,
    u128,
    u128,
    Option<Vec<u64>>,
    usize,
    usize,
    usize,
    usize,
    Option<String>,
);

/// The entire finite section loop runs here. Denominators and output masses are
/// reused; a strict incumbent loss is a certified lower bound for that section.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature=(initial, boundaries, corrections, cycles, seed, weights, best_a, best_b, witness, quota, wall, cancellation=None))]
pub fn section_search(
    py: Python<'_>,
    initial: PyRef<'_, NativeMatrix>,
    boundaries: PyRef<'_, NativeMatrix>,
    corrections: PyRef<'_, NativeMatrix>,
    cycles: PyRef<'_, NativeMatrix>,
    seed: PyRef<'_, NativeMatrix>,
    weights: Vec<u128>,
    best_a: u128,
    best_b: u128,
    witness: Option<Vec<u64>>,
    quota: usize,
    wall: Option<f64>,
    cancellation: Option<PyRef<'_, super::CancellationFlag>>,
) -> PyResult<SectionSearch> {
    check_wall(wall)?;
    let n = initial.inner.n;
    if initial.inner.m != n
        || seed.inner.m != n
        || seed.inner.n != n
        || boundaries.inner.m != n
        || corrections.inner.n != n
        || cycles.inner.m != n
        || best_b == 0
    {
        return Err(PyValueError::new_err(
            "section search shapes or incumbent differ",
        ));
    }
    if let Some(z) = &witness {
        checked_vector(z, n)?;
    }
    let basis = cycles.inner.transpose()?.rows();
    let cycle_count = span_count(&basis, n, &weights)?;
    let width = boundaries
        .inner
        .n
        .checked_mul(corrections.inner.m)
        .ok_or_else(|| PyValueError::new_err("section count overflow"))?;
    let count = 1_usize
        .checked_shl(width.try_into().unwrap_or(u32::MAX))
        .ok_or_else(|| PyValueError::new_err("section count overflow"))?;
    if count
        .checked_mul(cycle_count.max(1))
        .is_none_or(|work| work > 100_000)
    {
        return Err(PyValueError::new_err("section replay support exceeded"));
    }
    let mut current = (*initial.inner).clone();
    let (f, delta, mut best) = (
        boundaries.inner.clone(),
        corrections.inner.clone(),
        (*seed.inner).clone(),
    );
    let cancellation = cancellation.map(|f| f.state.clone());
    py.detach(move || {
        let started = Instant::now();
        let (mut a, mut b, mut witness) = (best_a, best_b, witness);
        let mut inputs = Vec::with_capacity(cycle_count);
        let mut z = zeros(n.div_ceil(64))?;
        let mut reason = None;
        for encoded in 1..=cycle_count {
            if let Some(stop) = stopped(0, usize::MAX, started, wall, &cancellation) {
                reason = Some(stop);
                break;
            }
            span_step(&mut z, &basis, encoded - 1, encoded);
            inputs.push((z.clone(), mass(&z, &weights)));
        }
        let (mut visited, mut used, mut pruned) = (0, 0, 0);
        let mut cached = std::collections::HashMap::new();
        let mut best_columns = best.transpose()?.rows();
        let beta = delta.m;
        'search: for encoded in 0..count {
            if reason.is_some() {
                break;
            }
            if let Some(stop) = stopped(used, quota, started, wall, &cancellation) {
                reason = Some(stop);
                break;
            }
            used += 1;
            if encoded != 0 {
                let mut changed = (encoded - 1) ^ encoded;
                while changed != 0 {
                    let parameter = width - 1 - changed.trailing_zeros() as usize;
                    for i in 0..n {
                        if f.bit(i, parameter / beta) {
                            let mut row = current.row(i).to_vec();
                            delta.xor_into(parameter % beta, &mut row);
                            current.replace_row(i, &row);
                        }
                    }
                    changed &= changed - 1;
                }
            }
            let (mut ca, mut cb, mut cw) = (0, 1, None);
            let mut lost = false;
            for (z, denominator) in &inputs {
                if let Some(stop) = stopped(used, quota, started, wall, &cancellation) {
                    reason = Some(stop);
                    break 'search;
                }
                used += 1;
                let image = current.apply(z)?;
                let numerator = *cached
                    .entry(image.clone())
                    .or_insert_with(|| mass(&image, &weights));
                if cw.is_none() || ratio_greater(numerator, *denominator, ca, cb) {
                    ca = numerator;
                    cb = *denominator;
                    cw = Some(z.clone());
                }
                if ratio_greater(ca, cb, a, b) {
                    lost = true;
                    pruned += 1;
                    break;
                }
            }
            if !lost {
                let columns = current.transpose()?.rows();
                // Compare arbitrary-width packed columns as unsigned integers,
                // most significant word first, in original column order.
                let key_less = columns
                    .iter()
                    .zip(&best_columns)
                    .find_map(|(x, y)| {
                        let cmp = x.iter().rev().cmp(y.iter().rev());
                        (cmp != std::cmp::Ordering::Equal).then_some(cmp.is_lt())
                    })
                    .unwrap_or(false);
                let equal = !ratio_greater(ca, cb, a, b) && !ratio_greater(a, b, ca, cb);
                if ratio_greater(a, b, ca, cb) || (equal && key_less) {
                    best = current.clone();
                    a = ca;
                    b = cb;
                    witness = cw;
                    best_columns = columns;
                }
            }
            visited += 1;
        }
        Ok((
            NativeMatrix {
                inner: Arc::new(best),
            },
            a,
            b,
            witness,
            visited,
            used,
            pruned,
            cached.len(),
            reason,
        ))
    })
}

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

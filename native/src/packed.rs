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

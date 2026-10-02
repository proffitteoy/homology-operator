//! Single-threaded, one-word vertical prototype. Python remains the independent validator.
#![forbid(unsafe_code)]

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::time::Instant;

mod packed;

fn mask(n: usize) -> u64 {
    if n == 64 { u64::MAX } else { (1_u64 << n) - 1 }
}

fn check(rows: &[u64], m: usize, n: usize) -> PyResult<()> {
    if m > 64 || n > 64 || rows.len() != m {
        return Err(PyValueError::new_err(
            "prototype requires matching dimensions <=64",
        ));
    }
    if rows.iter().any(|row| row & !mask(n) != 0) {
        return Err(PyValueError::new_err("nonzero padding bits"));
    }
    Ok(())
}

fn identity(n: usize) -> Vec<u64> {
    (0..n).map(|i| 1_u64 << i).collect()
}

fn multiply(a: &[u64], b: &[u64]) -> Vec<u64> {
    a.iter()
        .map(|row| {
            let mut remaining = *row;
            let mut output = 0;
            while remaining != 0 {
                let j = remaining.trailing_zeros() as usize;
                output ^= b[j];
                remaining &= remaining - 1;
            }
            output
        })
        .collect()
}

struct Budget {
    started: Instant,
    states: usize,
    state_limit: usize,
    wall_limit: f64,
    entry_limit: usize,
}

impl Budget {
    fn step(&mut self) -> Result<(), &'static str> {
        if self.states >= self.state_limit {
            return Err("state_limit");
        }
        if self.started.elapsed().as_secs_f64() >= self.wall_limit {
            return Err("wall_time_limit");
        }
        self.states += 1;
        Ok(())
    }

    fn entries(&self, entries: usize) -> Result<(), &'static str> {
        if entries > self.entry_limit {
            Err("matrix_entry_limit")
        } else {
            Ok(())
        }
    }
}

fn inverse(rows: &[u64], n: usize, budget: &mut Budget) -> Result<Vec<u64>, &'static str> {
    budget.step()?;
    let m = rows.len();
    budget.entries(m * (n + m))?;
    let mut left = rows.to_vec();
    let mut right = identity(m);
    let mut pivots = Vec::new();
    let mut pivot_row = 0;
    // Match reference RREF of the WHOLE [M | I], including identity-side pivots.
    // These later row operations affect G and the noncycle extension of P.
    for col in 0..n + m {
        let selected = (pivot_row..m).find(|&i| {
            if col < n {
                (left[i] >> col) & 1 != 0
            } else {
                (right[i] >> (col - n)) & 1 != 0
            }
        });
        if let Some(selected) = selected {
            left.swap(pivot_row, selected);
            right.swap(pivot_row, selected);
            for i in 0..m {
                let bit = if col < n {
                    (left[i] >> col) & 1
                } else {
                    (right[i] >> (col - n)) & 1
                };
                if i != pivot_row && bit != 0 {
                    left[i] ^= left[pivot_row];
                    right[i] ^= right[pivot_row];
                }
            }
            pivots.push(col);
            pivot_row += 1;
            if pivot_row == m {
                break;
            }
        }
    }
    let mut g = vec![0; n];
    for (i, &col) in pivots.iter().enumerate() {
        if col < n {
            g[col] = right[i];
        }
        budget.step()?;
    }
    Ok(g)
}

type Construction = (Vec<u64>, Vec<u64>, Vec<u64>, usize, f64, Option<String>);

#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn construct(
    a: Vec<u64>,
    m: usize,
    n: usize,
    d: Vec<u64>,
    p: usize,
    state_limit: usize,
    wall_limit: f64,
    entry_limit: usize,
) -> PyResult<Construction> {
    check(&a, m, n)?;
    check(&d, n, p)?;
    if !wall_limit.is_finite() || wall_limit < 0.0 {
        return Err(PyValueError::new_err(
            "wall limit must be finite and nonnegative",
        ));
    }
    if multiply(&a, &d).iter().any(|&row| row != 0) {
        return Err(PyValueError::new_err("AD must be zero"));
    }
    let mut budget = Budget {
        started: Instant::now(),
        states: 0,
        state_limit,
        wall_limit,
        entry_limit,
    };
    let result = (|| {
        budget.step()?;
        budget.entries(m * n + n * p + n * m + p * n + 4 * n * n)?;
        let g = inverse(&a, n, &mut budget)?;
        let u = inverse(&d, p, &mut budget)?;
        budget.step()?;
        let r: Vec<_> = identity(n)
            .iter()
            .zip(multiply(&g, &a))
            .map(|(x, y)| x ^ y)
            .collect();
        let q: Vec<_> = identity(n)
            .iter()
            .zip(multiply(&d, &u))
            .map(|(x, y)| x ^ y)
            .collect();
        let projection = multiply(&q, &r);
        budget.step()?;
        Ok::<_, &'static str>((g, u, projection))
    })();
    let wall = budget.started.elapsed().as_secs_f64();
    Ok(match result {
        Ok((g, u, projection)) => (g, u, projection, budget.states, wall, None),
        Err(reason) => (
            vec![],
            vec![],
            vec![],
            budget.states,
            wall,
            Some(reason.to_owned()),
        ),
    })
}

type Batch = (Vec<u64>, Vec<u64>, Vec<Vec<usize>>, f64);

#[pyfunction]
fn actions(projection: Vec<u64>, n: usize, vectors: Vec<u64>) -> PyResult<Batch> {
    check(&projection, n, n)?;
    if vectors.iter().any(|x| x & !mask(n) != 0) {
        return Err(PyValueError::new_err("nonzero vector padding bits"));
    }
    let started = Instant::now();
    let mut projected = Vec::with_capacity(vectors.len());
    let mut applied = Vec::with_capacity(vectors.len());
    let mut supports = Vec::with_capacity(vectors.len());
    for x in vectors {
        let mut z = 0;
        let mut support = Vec::new();
        for (i, row) in projection.iter().enumerate() {
            if (row & x).count_ones() & 1 != 0 {
                z |= 1_u64 << i;
                support.push(i);
            }
        }
        projected.push(z);
        applied.push(x ^ z);
        supports.push(support);
    }
    Ok((
        projected,
        applied,
        supports,
        started.elapsed().as_secs_f64(),
    ))
}

#[pymodule]
fn _homology_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(construct, module)?)?;
    module.add_function(wrap_pyfunction!(actions, module)?)?;
    module.add_function(wrap_pyfunction!(packed::packed_add, module)?)?;
    module.add_function(wrap_pyfunction!(packed::packed_product, module)?)?;
    module.add_class::<packed::PreparedMatrix>()?;
    module.add_function(wrap_pyfunction!(packed::span_objective, module)?)?;
    module.add_function(wrap_pyfunction!(packed::span_table, module)?)?;
    module.add_function(wrap_pyfunction!(packed::packed_apply, module)?)?;
    module.add_function(wrap_pyfunction!(packed::cyclic_batch, module)?)?;

    module.add_function(wrap_pyfunction!(packed::compact_actions, module)?)?;
    module.add_class::<packed::GeometryWorkspace>()?;
    module.add("__version__", "0.0.2.dev0")?;
    Ok(())
}

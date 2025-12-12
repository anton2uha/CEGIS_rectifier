# Iterative SAT-Solving Rectifier
*Anthony Lesik and Byron Stewart, December 2025*

This repository contains our final project for [ECE5745](https://my.ece.utah.edu/~kalla/index_6745.html). It is further described in ProjectReport.md.

To run the program, install [Z3](https://github.com/Z3Prover/z3) and its Python bindings, and call `main.py`. An example call is 

```python
python3 main.py --impl benchmarks/example2_buggy.blif --spec benchmarks/example2_spec.blif --fix "t3"
"

```

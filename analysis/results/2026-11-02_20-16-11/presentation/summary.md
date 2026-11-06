# Presentation summary

## 32-bit key (RND320), 8 circuits: c432, c499, c880, c1355, c1908, c2670, c3540, c5315

| Method | Runs | Equivalent | Total queries | vs baseline | Geo-mean query ratio | Fewest queries on | Total I/O-aware runtime (s) | Fastest on |
|---|---|---|---|---|---|---|---|---|
| Standard SAT | 40 | 40/40 | 112.8 | +0% | 1.00 | 2/8 | 17.6 | 3/8 |
| Partitioning | 40 | 40/40 | 109.8 | -3% | 0.98 | 0/8 | 21.5 | 0/8 |
| MaxSAT (Hamming) | 40 | 40/40 | 87.4 | -23% | 0.74 | 6/8 | 18.7 | 5/8 |

Per circuit, mean oracle queries ± sample standard deviation over seeds:

| Circuit | Standard SAT | Partitioning | MaxSAT (Hamming) |
|---|---|---|---|
| c432 | 24.6 ± 8.3 | 19.2 ± 5.8 | 13.8 ± 2.8 |
| c499 | 12.0 ± 3.0 | 12.2 ± 4.5 | 15.4 ± 4.6 |
| c880 | 7.6 ± 0.9 | 6.2 ± 0.8 | 4.2 ± 0.4 |
| c1355 | 17.0 ± 5.7 | 17.8 ± 7.4 | 19.6 ± 1.9 |
| c1908 | 9.8 ± 2.7 | 12.2 ± 1.3 | 8.2 ± 1.5 |
| c2670 | 16.6 ± 4.2 | 16.2 ± 4.1 | 11.4 ± 1.1 |
| c3540 | 14.0 ± 1.2 | 13.8 ± 0.8 | 8.4 ± 0.9 |
| c5315 | 11.2 ± 1.1 | 12.2 ± 1.8 | 6.4 ± 0.5 |

## 64-bit key (RND640), 8 circuits: c432, c499, c880, c1355, c1908, c2670, c3540, c5315

| Method | Runs | Equivalent | Total queries | vs baseline | Geo-mean query ratio | Fewest queries on | Total I/O-aware runtime (s) | Fastest on |
|---|---|---|---|---|---|---|---|---|
| Standard SAT | 40 | 40/40 | 303.0 | +0% | 1.00 | 0/8 | 44.0 | 5/8 |
| Partitioning | 40 | 40/40 | 297.2 | -2% | 0.96 | 1/8 | 59.6 | 0/8 |
| MaxSAT (Hamming) | 40 | 40/40 | 202.2 | -33% | 0.64 | 7/8 | 83.3 | 3/8 |

Per circuit, mean oracle queries ± sample standard deviation over seeds:

| Circuit | Standard SAT | Partitioning | MaxSAT (Hamming) |
|---|---|---|---|
| c432 | 42.6 ± 25.5 | 54.4 ± 17.5 | 21.2 ± 5.2 |
| c499 | 21.2 ± 4.5 | 23.0 ± 6.1 | 19.0 ± 1.2 |
| c880 | 15.0 ± 4.8 | 12.8 ± 2.0 | 10.2 ± 2.4 |
| c1355 | 38.0 ± 12.1 | 33.8 ± 7.2 | 50.6 ± 23.3 |
| c1908 | 49.2 ± 19.6 | 33.6 ± 15.5 | 26.8 ± 14.4 |
| c2670 | 84.0 ± 42.3 | 85.6 ± 46.8 | 49.6 ± 20.6 |
| c3540 | 24.6 ± 2.1 | 23.2 ± 2.0 | 13.2 ± 0.8 |
| c5315 | 28.4 ± 1.8 | 30.8 ± 3.1 | 11.6 ± 1.3 |

## 128-bit key (RND1280), 6 circuits: c432, c499, c880, c1908, c3540, c5315

Excluded, some runs timed out: c1355, c2670

| Method | Runs | Equivalent | Total queries | vs baseline | Geo-mean query ratio | Fewest queries on | Total I/O-aware runtime (s) | Fastest on |
|---|---|---|---|---|---|---|---|---|
| Standard SAT | 30 | 30/30 | 302.4 | +0% | 1.00 | 0/6 | 89.3 | 4/6 |
| Partitioning | 30 | 30/30 | 269.4 | -11% | 0.89 | 2/6 | 125.6 | 0/6 |
| MaxSAT (Hamming) | 30 | 30/30 | 304.8 | +1% | 0.75 | 4/6 | 316.9 | 2/6 |

Per circuit, mean oracle queries ± sample standard deviation over seeds:

| Circuit | Standard SAT | Partitioning | MaxSAT (Hamming) |
|---|---|---|---|
| c432 | 83.6 ± 36.6 | 73.8 ± 15.2 | 150.2 ± 84.2 |
| c499 | 37.4 ± 4.9 | 33.2 ± 8.6 | 60.8 ± 9.4 |
| c880 | 34.8 ± 4.9 | 27.8 ± 4.7 | 13.6 ± 1.1 |
| c1908 | 55.2 ± 12.3 | 43.8 ± 8.9 | 37.8 ± 9.7 |
| c3540 | 37.8 ± 4.1 | 36.4 ± 4.4 | 19.8 ± 0.8 |
| c5315 | 53.6 ± 4.0 | 54.4 ± 6.1 | 22.6 ± 1.9 |

# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/anzalks/synaptipy/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                               |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/Synaptipy/core/\_\_init\_\_.py                 |        2 |        0 |    100% |           |
| src/Synaptipy/core/analysis/\_\_init\_\_.py        |       13 |        0 |    100% |           |
| src/Synaptipy/core/analysis/batch\_engine.py       |      475 |       16 |     97% |680-681, 683, 731-733, 842, 851, 877, 885, 1086-1093 |
| src/Synaptipy/core/analysis/cross\_file\_utils.py  |       56 |        1 |     98% |        78 |
| src/Synaptipy/core/analysis/epoch\_manager.py      |       96 |        8 |     92% |281-286, 290-291 |
| src/Synaptipy/core/analysis/evoked\_responses.py   |      278 |        8 |     97% |311, 331, 388, 392, 413-423 |
| src/Synaptipy/core/analysis/firing\_dynamics.py    |      233 |        7 |     97% |91, 139-140, 387, 546, 649-650 |
| src/Synaptipy/core/analysis/passive\_properties.py |      755 |       15 |     98% |128, 151-152, 216, 304, 847-849, 962-967, 1007-1008, 1461-1462 |
| src/Synaptipy/core/analysis/registry.py            |       96 |        6 |     94% |     57-66 |
| src/Synaptipy/core/analysis/single\_spike.py       |      366 |       22 |     94% |115, 133, 138-139, 162-164, 212, 216-217, 411, 416, 476, 539-545, 627, 797-799 |
| src/Synaptipy/core/analysis/synaptic\_events.py    |      491 |       39 |     92% |281-283, 335, 377, 416, 419-443, 459, 464, 587-589, 700-702, 812, 927, 957, 973, 1026-1028, 1148, 1233, 1247, 1266-1267, 1368 |
| src/Synaptipy/core/data\_model.py                  |      265 |       14 |     95% |206, 209-210, 239, 324-326, 345, 363-365, 412-414, 534 |
| src/Synaptipy/core/processing\_pipeline.py         |      137 |        0 |    100% |           |
| src/Synaptipy/core/results.py                      |       91 |        0 |    100% |           |
| src/Synaptipy/core/signal\_processor.py            |      368 |        1 |     99% |        95 |
| src/Synaptipy/core/source\_interfaces.py           |        2 |        0 |    100% |           |
| **TOTAL**                                          | **3724** |  **137** | **96%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/anzalks/synaptipy/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/anzalks/synaptipy/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/anzalks/synaptipy/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/anzalks/synaptipy/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fanzalks%2Fsynaptipy%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/anzalks/synaptipy/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.
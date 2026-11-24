# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/anzalks/synaptipy/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/synaptipy/\_\_init\_\_.py                                       |        5 |        0 |    100% |           |
| src/synaptipy/application/\_\_init\_\_.py                           |        1 |        0 |    100% |           |
| src/synaptipy/application/cli/\_\_init\_\_.py                       |        2 |        0 |    100% |           |
| src/synaptipy/application/cli/main.py                               |       74 |        1 |     99% |        93 |
| src/synaptipy/application/controllers/\_\_init\_\_.py               |        6 |        0 |    100% |           |
| src/synaptipy/application/controllers/live\_analysis\_controller.py |       65 |        0 |    100% |           |
| src/synaptipy/application/data\_loader.py                           |       99 |        0 |    100% |           |
| src/synaptipy/application/gui/\_\_init\_\_.py                       |        1 |        0 |    100% |           |
| src/synaptipy/application/gui/analysis\_tabs/\_\_init\_\_.py        |        3 |        0 |    100% |           |
| src/synaptipy/application/gui/dialogs/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| src/synaptipy/application/gui/dialogs/protocol\_map\_dialog.py      |      164 |       15 |     91% |134, 141, 144, 151, 155, 177-179, 203, 227-232 |
| src/synaptipy/application/gui/explorer/\_\_init\_\_.py              |        2 |        0 |    100% |           |
| src/synaptipy/application/gui/explorer/toolbar.py                   |       80 |        0 |    100% |           |
| src/synaptipy/application/gui/widgets/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| src/synaptipy/application/services/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| src/synaptipy/application/services/data\_loader\_service.py         |       88 |        3 |     97% |119-120, 153 |
| src/synaptipy/application/services/methods\_generator.py            |       42 |        1 |     98% |        46 |
| src/synaptipy/application/services/parameter\_templates.py          |       61 |        7 |     89% | 33, 42-47 |
| src/synaptipy/application/session\_manager.py                       |      214 |        2 |     99% |     86-87 |
| src/synaptipy/core/\_\_init\_\_.py                                  |        2 |        0 |    100% |           |
| src/synaptipy/core/analysis/\_\_init\_\_.py                         |       16 |        0 |    100% |           |
| src/synaptipy/core/analysis/batch\_engine.py                        |      958 |      102 |     89% |122, 133, 145, 155, 275, 278-281, 283, 731, 739, 753, 763-770, 772-773, 794-804, 820, 826-837, 872, 878, 916, 938, 962, 971-972, 982, 1022-1023, 1192-1193, 1195, 1243-1245, 1278-1279, 1289-1290, 1350, 1407, 1422, 1433, 1470-1472, 1506-1508, 1556-1558, 1566-1590, 1598-1599, 1606-1610, 1616-1620, 1639-1640, 1665-1667, 1698-1700, 1720-1721, 1768-1770, 1782, 1875, 1877-1878, 1885, 1891, 1904, 1941-1953, 1956-1968, 1985, 2019-2021, 2111 |
| src/synaptipy/core/analysis/contracts.py                            |       50 |        1 |     98% |        38 |
| src/synaptipy/core/analysis/cross\_file\_utils.py                   |      234 |        1 |     99% |       388 |
| src/synaptipy/core/analysis/epoch\_manager.py                       |      109 |        3 |     97% |54, 302, 308 |
| src/synaptipy/core/analysis/evoked\_responses.py                    |      658 |       37 |     94% |469, 473, 620, 627, 746, 753-754, 757-780, 801-802, 1130, 1216, 1235-1236, 1321, 1332, 1334, 1536-1543, 1694, 1870, 1893, 1922 |
| src/synaptipy/core/analysis/firing\_dynamics.py                     |      310 |        1 |     99% |       693 |
| src/synaptipy/core/analysis/passive\_properties.py                  |      872 |       24 |     97% |174, 279, 294, 401-405, 442, 808-812, 1080, 1152, 1245, 1282-1283, 2107-2110, 2489 |
| src/synaptipy/core/analysis/preprocessing.py                        |       75 |       38 |     49% |23-34, 53, 55-57, 59-62, 68, 84-87, 93-97, 105-107, 113-117, 125-128 |
| src/synaptipy/core/analysis/registry.py                             |      128 |        2 |     98% |   192-196 |
| src/synaptipy/core/analysis/single\_spike.py                        |      563 |       28 |     95% |197-198, 510, 541, 585, 591, 643, 671, 801-807, 873, 882-884, 891, 1131-1137, 1203-1205, 1302, 1329-1331 |
| src/synaptipy/core/analysis/synaptic\_events.py                     |      520 |       25 |     95% |303-304, 351, 432, 435-459, 915-916, 982, 989, 1009, 1071, 1088, 1119 |
| src/synaptipy/core/averaging.py                                     |       32 |        1 |     97% |        46 |
| src/synaptipy/core/constants.py                                     |       15 |        0 |    100% |           |
| src/synaptipy/core/data\_model.py                                   |      310 |        7 |     98% |142, 144, 161-163, 304, 329 |
| src/synaptipy/core/error\_handler.py                                |       77 |        1 |     99% |       138 |
| src/synaptipy/core/processing\_pipeline.py                          |      184 |       13 |     93% |179-183, 261-272 |
| src/synaptipy/core/protocols.py                                     |      191 |        2 |     99% |   296-297 |
| src/synaptipy/core/results.py                                       |      149 |        0 |    100% |           |
| src/synaptipy/core/signal\_processor.py                             |      459 |        8 |     98% |202-203, 213, 231, 241, 250, 503, 513 |
| src/synaptipy/core/source\_interfaces.py                            |        2 |        0 |    100% |           |
| src/synaptipy/core/trial\_qc.py                                     |       32 |        1 |     97% |        47 |
| src/synaptipy/infrastructure/\_\_init\_\_.py                        |        1 |        0 |    100% |           |
| src/synaptipy/infrastructure/exporters/\_\_init\_\_.py              |        2 |        0 |    100% |           |
| src/synaptipy/infrastructure/exporters/csv\_exporter.py             |      378 |        5 |     99% |22-23, 60-61, 298 |
| src/synaptipy/infrastructure/exporters/nwb\_exporter.py             |      428 |       53 |     88% |36-37, 103-121, 273, 277, 295-298, 463-464, 493, 511-512, 525-526, 529, 600, 619-621, 667-669, 679-681, 756-771, 854-855, 869, 900-901, 921-922, 929-932 |
| src/synaptipy/infrastructure/file\_readers/\_\_init\_\_.py          |        2 |        0 |    100% |           |
| src/synaptipy/infrastructure/file\_readers/abf\_reader.py           |        0 |        0 |    100% |           |
| src/synaptipy/infrastructure/file\_readers/format\_support.py       |       12 |        0 |    100% |           |
| src/synaptipy/infrastructure/file\_readers/neo\_adapter.py          |      719 |      112 |     84% |55-56, 158-159, 165, 170-175, 181, 185, 221, 234-236, 278, 303, 331-333, 343-345, 401, 404, 410, 414, 460, 463, 599-602, 636-637, 673-690, 706-709, 734, 747-757, 760, 834-837, 855, 920-931, 933-934, 943-946, 960, 970, 1038-1039, 1122, 1146, 1172-1179, 1185, 1219-1220, 1229-1231, 1272-1273, 1295-1297, 1348-1351, 1393, 1395 |
| src/synaptipy/infrastructure/file\_readers/neo\_source\_handle.py   |       69 |        7 |     90% |43-47, 60-61 |
| src/synaptipy/infrastructure/neo\_patches.py                        |      161 |        7 |     96% |79-80, 93-94, 135-139, 201 |
| src/synaptipy/shared/\_\_init\_\_.py                                |       16 |        0 |    100% |           |
| src/synaptipy/shared/constants.py                                   |       11 |        0 |    100% |           |
| src/synaptipy/shared/cursor\_manager.py                             |      196 |       17 |     91% |72-79, 95, 97, 101, 125, 130, 134, 144, 148, 162-163 |
| src/synaptipy/shared/data\_cache.py                                 |      154 |        1 |     99% |        55 |
| src/synaptipy/shared/error\_handling.py                             |       20 |        0 |    100% |           |
| src/synaptipy/shared/logging\_config.py                             |       88 |        4 |     95% |121-122, 153-154 |
| src/synaptipy/shared/scroll\_settings.py                            |       53 |        1 |     98% |        93 |
| src/synaptipy/shared/utils.py                                       |       84 |        6 |     93% |     80-85 |
| src/synaptipy/shared/xlsx\_exporter.py                              |       97 |        7 |     93% |73, 80-81, 95-96, 115, 117 |
| src/synaptipy/templates/\_\_init\_\_.py                             |        0 |        0 |    100% |           |
| src/synaptipy/templates/plugin\_template.py                         |       13 |        0 |    100% |           |
| **TOTAL**                                                           | **9357** |  **544** | **94%** |           |


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
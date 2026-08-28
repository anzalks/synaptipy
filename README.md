# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/anzalks/synaptipy/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/synaptipy/\_\_init\_\_.py                                       |        5 |        0 |    100% |           |
| src/synaptipy/application/\_\_init\_\_.py                           |        1 |        0 |    100% |           |
| src/synaptipy/application/cli/\_\_init\_\_.py                       |        2 |        0 |    100% |           |
| src/synaptipy/application/cli/main.py                               |       64 |        1 |     98% |        81 |
| src/synaptipy/application/controllers/\_\_init\_\_.py               |        6 |        0 |    100% |           |
| src/synaptipy/application/controllers/live\_analysis\_controller.py |       65 |        0 |    100% |           |
| src/synaptipy/application/data\_loader.py                           |       95 |        0 |    100% |           |
| src/synaptipy/application/gui/\_\_init\_\_.py                       |        1 |        0 |    100% |           |
| src/synaptipy/application/gui/analysis\_tabs/\_\_init\_\_.py        |        3 |        0 |    100% |           |
| src/synaptipy/application/gui/dialogs/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| src/synaptipy/application/gui/dialogs/protocol\_map\_dialog.py      |      164 |       15 |     91% |134, 141, 144, 151, 155, 177-179, 203, 227-232 |
| src/synaptipy/application/gui/explorer/\_\_init\_\_.py              |        2 |        0 |    100% |           |
| src/synaptipy/application/gui/explorer/toolbar.py                   |       80 |        0 |    100% |           |
| src/synaptipy/application/gui/widgets/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| src/synaptipy/application/services/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| src/synaptipy/application/services/data\_loader\_service.py         |       36 |        1 |     97% |        92 |
| src/synaptipy/application/services/methods\_generator.py            |       33 |        0 |    100% |           |
| src/synaptipy/application/services/parameter\_templates.py          |       42 |        0 |    100% |           |
| src/synaptipy/application/session\_manager.py                       |      190 |        0 |    100% |           |
| src/synaptipy/core/\_\_init\_\_.py                                  |        2 |        0 |    100% |           |
| src/synaptipy/core/analysis/\_\_init\_\_.py                         |       15 |        0 |    100% |           |
| src/synaptipy/core/analysis/batch\_engine.py                        |      807 |       95 |     88% |189, 192-195, 197, 633, 640-642, 653, 717, 759, 777, 971-972, 974, 1022-1024, 1063-1064, 1138, 1154, 1163, 1187, 1229-1231, 1260-1270, 1279, 1282, 1299-1300, 1341, 1349-1402, 1413-1417, 1436-1437, 1462-1464, 1495-1497, 1517-1518, 1576, 1588, 1668-1674, 1679, 1685, 1693-1696, 1717, 1732-1744, 1747-1759, 1803-1805, 1894 |
| src/synaptipy/core/analysis/contracts.py                            |       34 |        0 |    100% |           |
| src/synaptipy/core/analysis/cross\_file\_utils.py                   |      234 |        1 |     99% |       388 |
| src/synaptipy/core/analysis/epoch\_manager.py                       |      107 |        3 |     97% |54, 290, 296 |
| src/synaptipy/core/analysis/evoked\_responses.py                    |      593 |       19 |     97% |430, 434, 588, 604, 698, 723-736, 1087, 1155, 1179-1180, 1260, 1271, 1273, 1758, 1781, 1810 |
| src/synaptipy/core/analysis/firing\_dynamics.py                     |      292 |        0 |    100% |           |
| src/synaptipy/core/analysis/passive\_properties.py                  |      798 |       18 |     98% |156, 352-356, 393, 759-763, 1014, 1144-1150, 1208-1209 |
| src/synaptipy/core/analysis/registry.py                             |      128 |        2 |     98% |   192-196 |
| src/synaptipy/core/analysis/single\_spike.py                        |      428 |       13 |     97% |165, 188-189, 489, 587, 718-724, 1001-1003 |
| src/synaptipy/core/analysis/synaptic\_events.py                     |      453 |       21 |     95% |280-282, 334, 417, 420-444, 857-858, 977, 993 |
| src/synaptipy/core/averaging.py                                     |       32 |        1 |     97% |        46 |
| src/synaptipy/core/constants.py                                     |       15 |        0 |    100% |           |
| src/synaptipy/core/data\_model.py                                   |      276 |        5 |     98% |216-217, 278-280 |
| src/synaptipy/core/error\_handler.py                                |       77 |        1 |     99% |       138 |
| src/synaptipy/core/processing\_pipeline.py                          |      157 |        0 |    100% |           |
| src/synaptipy/core/protocols.py                                     |      191 |        2 |     99% |   296-297 |
| src/synaptipy/core/results.py                                       |      149 |        0 |    100% |           |
| src/synaptipy/core/signal\_processor.py                             |      395 |        0 |    100% |           |
| src/synaptipy/core/source\_interfaces.py                            |        2 |        0 |    100% |           |
| src/synaptipy/core/trial\_qc.py                                     |       30 |        0 |    100% |           |
| src/synaptipy/infrastructure/\_\_init\_\_.py                        |        1 |        0 |    100% |           |
| src/synaptipy/infrastructure/exporters/\_\_init\_\_.py              |        2 |        0 |    100% |           |
| src/synaptipy/infrastructure/exporters/csv\_exporter.py             |      310 |        2 |     99% |     22-23 |
| src/synaptipy/infrastructure/exporters/nwb\_exporter.py             |      362 |       38 |     90% |36-37, 103-121, 380-381, 410, 428-429, 503, 522-524, 651-666, 716-717, 731, 762-763, 781-782, 789-792 |
| src/synaptipy/infrastructure/file\_readers/\_\_init\_\_.py          |        2 |        0 |    100% |           |
| src/synaptipy/infrastructure/file\_readers/abf\_reader.py           |        0 |        0 |    100% |           |
| src/synaptipy/infrastructure/file\_readers/format\_support.py       |       12 |        0 |    100% |           |
| src/synaptipy/infrastructure/file\_readers/neo\_adapter.py          |      591 |      144 |     76% |55-56, 158, 171-173, 215, 240, 268-270, 280-282, 338, 341, 347, 351, 397, 400, 536-539, 573-574, 604-646, 655-750, 770-773, 784-787, 796, 813, 847-848, 850-851, 855-863, 877, 885, 889, 953-954, 1162-1164, 1224-1228 |
| src/synaptipy/infrastructure/file\_readers/neo\_source\_handle.py   |       50 |        0 |    100% |           |
| src/synaptipy/infrastructure/neo\_patches.py                        |      154 |        3 |     98% |89-90, 188 |
| src/synaptipy/shared/\_\_init\_\_.py                                |       16 |        0 |    100% |           |
| src/synaptipy/shared/constants.py                                   |       11 |        0 |    100% |           |
| src/synaptipy/shared/cursor\_manager.py                             |      185 |       16 |     91% |47-54, 72, 99, 103, 113, 117, 130-131, 214-215 |
| src/synaptipy/shared/data\_cache.py                                 |      154 |        1 |     99% |        55 |
| src/synaptipy/shared/error\_handling.py                             |       20 |        0 |    100% |           |
| src/synaptipy/shared/logging\_config.py                             |       65 |        1 |     98% |        53 |
| src/synaptipy/shared/scroll\_settings.py                            |       53 |        1 |     98% |        93 |
| src/synaptipy/shared/utils.py                                       |       84 |        6 |     93% |     80-85 |
| src/synaptipy/shared/xlsx\_exporter.py                              |       62 |        0 |    100% |           |
| src/synaptipy/templates/\_\_init\_\_.py                             |        0 |        0 |    100% |           |
| src/synaptipy/templates/plugin\_template.py                         |       12 |        0 |    100% |           |
| **TOTAL**                                                           | **8150** |  **410** | **95%** |           |


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
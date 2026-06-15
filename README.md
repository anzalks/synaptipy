# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/anzalks/synaptipy/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                |    Stmts |     Miss |   Cover |   Missing |
|-------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| src/Synaptipy/\_\_init\_\_.py                                       |        5 |        0 |    100% |           |
| src/Synaptipy/application/\_\_init\_\_.py                           |        1 |        0 |    100% |           |
| src/Synaptipy/application/cli/\_\_init\_\_.py                       |        2 |        0 |    100% |           |
| src/Synaptipy/application/cli/main.py                               |        0 |        0 |    100% |           |
| src/Synaptipy/application/controllers/\_\_init\_\_.py               |        6 |        0 |    100% |           |
| src/Synaptipy/application/controllers/live\_analysis\_controller.py |       65 |        0 |    100% |           |
| src/Synaptipy/application/controllers/shortcut\_manager.py          |       20 |        3 |     85% |40, 51, 55 |
| src/Synaptipy/application/data\_loader.py                           |       93 |        0 |    100% |           |
| src/Synaptipy/application/gui/\_\_init\_\_.py                       |        1 |        0 |    100% |           |
| src/Synaptipy/application/gui/analysis\_tabs/\_\_init\_\_.py        |        3 |        0 |    100% |           |
| src/Synaptipy/application/gui/explorer/\_\_init\_\_.py              |        2 |        0 |    100% |           |
| src/Synaptipy/application/gui/explorer/toolbar.py                   |       80 |        0 |    100% |           |
| src/Synaptipy/application/gui/widgets/log\_streamer.py              |       97 |        6 |     94% |199, 240, 244-246, 250 |
| src/Synaptipy/application/services/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| src/Synaptipy/application/services/data\_loader\_service.py         |       36 |        1 |     97% |        92 |
| src/Synaptipy/application/services/methods\_generator.py            |       33 |        0 |    100% |           |
| src/Synaptipy/application/services/parameter\_templates.py          |       42 |        0 |    100% |           |
| src/Synaptipy/application/session\_manager.py                       |      188 |        0 |    100% |           |
| src/Synaptipy/core/\_\_init\_\_.py                                  |        2 |        0 |    100% |           |
| src/Synaptipy/core/analysis/\_\_init\_\_.py                         |       13 |        0 |    100% |           |
| src/Synaptipy/core/analysis/batch\_engine.py                        |      614 |       72 |     88% |198, 566, 572-579, 585, 589, 612-613, 618, 628, 632-633, 653, 661-669, 688-690, 702-703, 857-858, 860, 908-910, 941-942, 996, 1042-1052, 1061, 1064, 1081-1082, 1122, 1130-1151, 1162-1166, 1204-1206, 1236-1238, 1408-1430 |
| src/Synaptipy/core/analysis/cross\_file\_utils.py                   |      135 |       12 |     91% |27, 252-253, 267-271, 286-287, 361, 371-375 |
| src/Synaptipy/core/analysis/epoch\_manager.py                       |       96 |        0 |    100% |           |
| src/Synaptipy/core/analysis/evoked\_responses.py                    |      394 |       12 |     97% |373, 430, 434, 455-465, 796, 1038-1040, 1369 |
| src/Synaptipy/core/analysis/firing\_dynamics.py                     |      270 |        2 |     99% |   765-766 |
| src/Synaptipy/core/analysis/passive\_properties.py                  |      790 |       26 |     97% |156, 185, 248, 352-356, 393, 759-763, 1006-1018, 1149-1155, 1213-1214 |
| src/Synaptipy/core/analysis/registry.py                             |       96 |        0 |    100% |           |
| src/Synaptipy/core/analysis/single\_spike.py                        |      329 |       13 |     96% |154, 177-178, 387, 454, 539-545, 797-799 |
| src/Synaptipy/core/analysis/synaptic\_events.py                     |      519 |       22 |     96% |285-287, 339, 422, 425-449, 856-857, 976, 992, 1337 |
| src/Synaptipy/core/constants.py                                     |       15 |        0 |    100% |           |
| src/Synaptipy/core/data\_model.py                                   |      288 |        5 |     98% |214-215, 276-278 |
| src/Synaptipy/core/error\_handler.py                                |       77 |        1 |     99% |       138 |
| src/Synaptipy/core/processing\_pipeline.py                          |      137 |        0 |    100% |           |
| src/Synaptipy/core/results.py                                       |      119 |        0 |    100% |           |
| src/Synaptipy/core/signal\_processor.py                             |      395 |        0 |    100% |           |
| src/Synaptipy/core/source\_interfaces.py                            |        2 |        0 |    100% |           |
| src/Synaptipy/infrastructure/\_\_init\_\_.py                        |        1 |        0 |    100% |           |
| src/Synaptipy/infrastructure/exporters/\_\_init\_\_.py              |        2 |        0 |    100% |           |
| src/Synaptipy/infrastructure/exporters/csv\_exporter.py             |      311 |        2 |     99% |     22-23 |
| src/Synaptipy/infrastructure/exporters/nwb\_exporter.py             |      361 |       67 |     81% |36-37, 103-121, 223-224, 336, 338, 343, 345, 347, 359, 379-380, 409, 427-428, 480, 482, 502, 521-523, 528, 565-568, 570-573, 650-665, 686, 690, 704-714, 730, 758-759, 777-778, 785-788 |
| src/Synaptipy/infrastructure/file\_readers/\_\_init\_\_.py          |        2 |        0 |    100% |           |
| src/Synaptipy/infrastructure/file\_readers/abf\_reader.py           |        0 |        0 |    100% |           |
| src/Synaptipy/infrastructure/file\_readers/neo\_adapter.py          |      426 |       34 |     92% |52-53, 153, 166-168, 235, 263-265, 275-277, 407-410, 444-445, 493, 537-538, 540-541, 555, 563, 628-629, 837-839, 899-903 |
| src/Synaptipy/infrastructure/file\_readers/neo\_source\_handle.py   |       50 |        0 |    100% |           |
| src/Synaptipy/infrastructure/neo\_patches.py                        |      153 |       18 |     88% |49-50, 58-59, 87-90, 118-120, 128, 174, 187-189, 197-198 |
| src/Synaptipy/shared/\_\_init\_\_.py                                |       10 |        0 |    100% |           |
| src/Synaptipy/shared/constants.py                                   |       11 |        0 |    100% |           |
| src/Synaptipy/shared/cursor\_manager.py                             |      185 |       16 |     91% |47-54, 72, 99, 103, 113, 117, 130-131, 214-215 |
| src/Synaptipy/shared/data\_cache.py                                 |      128 |        1 |     99% |        55 |
| src/Synaptipy/shared/error\_handling.py                             |       20 |        0 |    100% |           |
| src/Synaptipy/shared/logging\_config.py                             |       65 |        1 |     98% |        53 |
| src/Synaptipy/shared/scroll\_settings.py                            |       53 |        1 |     98% |        93 |
| src/Synaptipy/shared/utils.py                                       |       84 |        6 |     93% |     80-85 |
| src/Synaptipy/templates/plugin\_template.py                         |       12 |        0 |    100% |           |
| **TOTAL**                                                           | **6839** |  **321** | **95%** |           |


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
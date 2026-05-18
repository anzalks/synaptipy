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
| src/Synaptipy/application/gui/explorer/config\_panel.py             |      244 |       21 |     91% |295-298, 313, 320, 327, 340, 352-354, 357-363, 368-372 |
| src/Synaptipy/application/gui/explorer/plot\_canvas.py              |      324 |       77 |     76% |63, 66, 69-70, 78, 81, 91, 94, 98-99, 105, 109-110, 121, 128-129, 164, 185-186, 192-193, 206, 210-212, 245-247, 252, 261-262, 321-322, 325-326, 329-330, 333-336, 354-358, 386-390, 435-436, 459-467, 480, 485-486, 496-499, 503-506, 510-511, 515-516 |
| src/Synaptipy/application/gui/explorer/toolbar.py                   |       80 |        0 |    100% |           |
| src/Synaptipy/application/gui/explorer/y\_controls.py               |      175 |       26 |     85% |131, 203-204, 210, 213-220, 223-225, 228-235, 238-240 |
| src/Synaptipy/application/gui/ui\_generator.py                      |      201 |       60 |     70% |29-40, 48, 52, 56, 60-61, 69-81, 108, 113-118, 221, 224-235, 245, 280-281, 295, 302-307, 314, 334-335, 345-350 |
| src/Synaptipy/application/services/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| src/Synaptipy/application/services/data\_loader\_service.py         |       32 |        1 |     97% |        92 |
| src/Synaptipy/application/services/methods\_generator.py            |       33 |        0 |    100% |           |
| src/Synaptipy/application/services/parameter\_templates.py          |       42 |        0 |    100% |           |
| src/Synaptipy/application/session\_manager.py                       |      188 |        0 |    100% |           |
| src/Synaptipy/core/\_\_init\_\_.py                                  |        2 |        0 |    100% |           |
| src/Synaptipy/core/analysis/\_\_init\_\_.py                         |       13 |        0 |    100% |           |
| src/Synaptipy/core/analysis/batch\_engine.py                        |      522 |       47 |     91% |197, 680-681, 683, 731-733, 764-765, 819, 865-875, 884, 887, 904-905, 945, 953-974, 985-989, 1027-1029, 1059-1061, 1231-1253 |
| src/Synaptipy/core/analysis/cross\_file\_utils.py                   |       59 |        0 |    100% |           |
| src/Synaptipy/core/analysis/epoch\_manager.py                       |       96 |        0 |    100% |           |
| src/Synaptipy/core/analysis/evoked\_responses.py                    |      394 |       12 |     97% |373, 430, 434, 455-465, 796, 1038-1040, 1369 |
| src/Synaptipy/core/analysis/firing\_dynamics.py                     |      270 |        2 |     99% |   765-766 |
| src/Synaptipy/core/analysis/passive\_properties.py                  |      776 |       16 |     98% |155, 184, 247, 382, 983-995, 1123-1128, 1186-1187 |
| src/Synaptipy/core/analysis/registry.py                             |       96 |        0 |    100% |           |
| src/Synaptipy/core/analysis/single\_spike.py                        |      367 |       13 |     96% |154, 177-178, 454, 519, 582-588, 840-842 |
| src/Synaptipy/core/analysis/synaptic\_events.py                     |      516 |       22 |     96% |285-287, 339, 422, 425-449, 856-857, 976, 992, 1304 |
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
| src/Synaptipy/infrastructure/file\_readers/\_\_init\_\_.py          |        2 |        0 |    100% |           |
| src/Synaptipy/infrastructure/file\_readers/abf\_reader.py           |        0 |        0 |    100% |           |
| src/Synaptipy/infrastructure/file\_readers/neo\_adapter.py          |      364 |       35 |     90% |52-53, 153, 166-168, 235, 263-265, 275-277, 374-379, 391-400, 405, 468-469, 677-679, 739-743 |
| src/Synaptipy/infrastructure/file\_readers/neo\_source\_handle.py   |       50 |        0 |    100% |           |
| src/Synaptipy/infrastructure/neo\_patches.py                        |      153 |       18 |     88% |49-50, 58-59, 87-90, 118-120, 128, 174, 187-189, 197-198 |
| src/Synaptipy/shared/\_\_init\_\_.py                                |       10 |        0 |    100% |           |
| src/Synaptipy/shared/constants.py                                   |       11 |        0 |    100% |           |
| src/Synaptipy/shared/cursor\_manager.py                             |      185 |       29 |     84% |85-88, 91-122 |
| src/Synaptipy/shared/data\_cache.py                                 |      128 |        1 |     99% |        55 |
| src/Synaptipy/shared/error\_handling.py                             |       20 |        0 |    100% |           |
| src/Synaptipy/shared/logging\_config.py                             |       65 |        1 |     98% |        53 |
| src/Synaptipy/shared/scroll\_settings.py                            |       53 |        1 |     98% |        93 |
| src/Synaptipy/shared/utils.py                                       |       84 |        6 |     93% |     80-85 |
| src/Synaptipy/templates/plugin\_template.py                         |       12 |        0 |    100% |           |
| **TOTAL**                                                           | **7112** |  **399** | **94%** |           |


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
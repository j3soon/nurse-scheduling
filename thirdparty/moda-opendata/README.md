# 中華民國政府行政機關辦公日曆表 ｜ 政府資料開放平臺

CSV downloaded from MODA Open Data <https://data.gov.tw/dataset/14718> without modification.

## Usage

Run the scripts from this directory with uv. Each script declares its
dependencies in inline script metadata, so uv installs them in a temporary
environment.

```sh
# print the entries for web-frontend/src/utils/taiwanHolidays.ts
uv run parse.py
# check the parser and compare its output with taiwanHolidays.ts
uv run test_parse.py
# print the public holidays from the holidays package for comparison
uv run print_holidays.py
```

Add each new year's CSV to the `filenames` list in `parse.py`.

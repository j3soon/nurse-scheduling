import holidays

for year in range(2023, 2027):
    for date, name in sorted(holidays.TW(years=year, categories=holidays.PUBLIC).items()):
        print(date, name)

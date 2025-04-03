import holidays

for date, name in sorted(holidays.TW(years=2025, categories=holidays.PUBLIC).items()):
    print(date, name)

# Test Fixtures

These fixtures are synthetic. They are designed to be small, private, and stable enough to use as golden data while API response schemas, route tests, and import preview behavior are built.

## Files

- `fortuneo_golden.csv`: main Fortuneo-style transaction fixture.
- `fortuneo_duplicate_rows.csv`: tiny CSV with an intentional duplicate inside the same upload.
- `HistoriqueOperationsBourse_mapping.csv`: source CSV for the synthetic Fortuneo bourse ZIP mapping fixture.
- `fortuneo_bourse_mapping.zip`: Fortuneo bourse ZIP shape with multiple rows that need ticker mappings.
- `market_history_basic.json`: manual historical prices for holdings plus S&P 500 and Nasdaq 100 benchmark series.
- `expected_portfolio_summary.json`: exact portfolio summary expected after importing `fortuneo_golden.csv` and applying the latest prices in `market_history_basic.json`.
- `expected_import_preview.json`: suggested import-preview shape for the golden CSV.
- `expected_duplicate_preview.json`: suggested import-preview shape for duplicate row handling.

## Coverage Intent

The golden CSV covers:

- multiple buys of the same ETF at different prices;
- partial sells and average cost reduction;
- transaction fees;
- a dividend row;
- two accounts, `PEA` and `CTO`;
- French decimal formatting;
- optional account and description fields.

The synthetic bourse ZIP covers real Fortuneo bourse headers with security labels but no ticker column. It is safe mock data and should be used instead of real account exports for regression tests.

Money values in expected JSON files are stored as strings to keep decimal precision exact.

## Telehealth GTM Conversion Scorer — Pipeline Runner
## Requires: make (use WSL or Git Bash on Windows)

.PHONY: all install generate dbt-seed dbt-run dbt-test train score clean

all: install generate dbt-seed dbt-run dbt-test train score

install:
	pip install -r requirements.txt

generate:
	python generate_data.py

dbt-seed:
	dbt seed --profiles-dir .

dbt-run:
	dbt run --profiles-dir .

dbt-test:
	dbt test --profiles-dir .

train:
	python train_model.py

score:
	python score_and_rank.py

clean:
	dbt clean --profiles-dir .
	rm -f telehealth_gtm.duckdb
	rm -rf outputs/ artifacts/

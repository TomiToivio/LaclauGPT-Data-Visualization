.PHONY: legacy-test legacy-pledge legacy-art

legacy-test:
	pytest tests/test_legacy_specialized.py
	npm run test:legacy

legacy-pledge:
	@test -n "$(INPUT)" || (echo "usage: make legacy-pledge INPUT=/private/pledge.csv OUTPUT=data/legacy/pledge" && exit 2)
	python -m scripts.legacy.pledge.preprocess "$(INPUT)" "$(or $(OUTPUT),data/legacy/pledge)"

legacy-art:
	@test -n "$(INPUT)" || (echo "usage: make legacy-art INPUT=/private/art.csv OUTPUT=data/legacy/art" && exit 2)
	python -m scripts.legacy.art.preprocess "$(INPUT)" "$(or $(OUTPUT),data/legacy/art)"

"""Assert what the seed actually left in the database."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.db.session import session_scope
from app.models.past_product import PastProduct
from app.models.product import Product
from app.models.score import Score
from app.models.user import User

REQUIRED_COLUMNS = (
    "title",
    "category",
    "price",
    "rating",
    "reviews_count",
    "product_url",
    "image_url",
)

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        failures.append(message)


def main() -> int:
    with session_scope() as db:
        users = db.query(User).all()
        products = db.query(Product).all()
        past_products = db.query(PastProduct).all()
        scores = db.query(Score).all()

        print("Admin account")
        admins = [u for u in users if u.username == settings.admin_username]
        check(len(admins) == 1, f"exactly one '{settings.admin_username}' (found {len(admins)})")

        print("Demo products")
        check(len(products) > 0, f"products were seeded (found {len(products)})")
        asins = [p.asin for p in products]
        check(len(asins) == len(set(asins)), "no duplicate ASINs after seeding twice")

        for column in REQUIRED_COLUMNS:
            check(
                hasattr(Product, column),
                f"the products table has the required column '{column}'",
            )

        for column in ("title", "category", "product_url", "reviews_count"):
            populated = sum(1 for p in products if getattr(p, column) is not None)
            check(populated == len(products), f"every product has a '{column}'")

        for column in ("price", "rating", "image_url"):
            populated = sum(1 for p in products if getattr(p, column) is not None)
            check(populated > 0, f"at least some products have a '{column}' ({populated})")

        print("Sales Boost history")
        check(len(past_products) > 0, f"past products were seeded (found {len(past_products)})")
        titles = [(p.title.lower(), p.category.lower()) for p in past_products]
        check(len(titles) == len(set(titles)), "no duplicate past products after seeding twice")

        print("Scores")
        check(len(scores) > 0, f"products were scored (found {len(scores)})")
        check(
            len({s.product_id for s in scores}) == len(products),
            "every product carries a score, so the dashboard is not half empty",
        )
        check(
            all(0 <= s.score <= 100 for s in scores),
            "every score sits within 0-100",
        )
        check(
            all(s.reasoning and s.reasoning.strip() for s in scores),
            "every score carries a non-empty reasoning",
        )
        check(
            all(s.provider == "fallback" for s in scores),
            "the seed scored with the formula, never calling an external API",
        )

    if failures:
        print(f"\n{len(failures)} check(s) failed.")
        return 1

    print("\nAll seed checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

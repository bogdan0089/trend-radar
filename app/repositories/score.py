from app.models.score import Score
from app.repositories.base import BaseRepository


class ScoreRepository(BaseRepository[Score]):
    model = Score

    def create(
        self,
        *,
        product_id: int,
        score: int,
        reasoning: str,
        provider: str,
        boost_score: int = 0,
        breakdown: dict | None = None,
    ) -> Score:
        """Append a new score; earlier ones are kept so the history stays visible."""
        return self.add(
            Score(
                product_id=product_id,
                score=score,
                reasoning=reasoning,
                provider=provider,
                boost_score=boost_score,
                breakdown=breakdown,
            )
        )

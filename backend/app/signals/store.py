"""Point-in-time read access to stored observations.

`ObservationRepository` loads observations once; `.at(as_of)` returns a view that only exposes
rows dated on or before `as_of`. The daily scan and historical replay share this code path.

Snapshot sources (rescaling indexes): a daily scan uses the latest snapshot whose window ends on
or before `as_of`. In replay, where no snapshot that old exists, it uses the earliest snapshot
covering `as_of`, truncated to `as_of`, and flags the series `rescaled_history`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Observation, Snapshot

EMPTY = pd.Series(dtype=float)


@dataclass(frozen=True)
class SeriesInfo:
    snapshot_id: int | None = None
    rescaled_history: bool = False


class ObservationRepository:
    def __init__(self, session: Session, sources: list[str] | None = None, since: date | None = None) -> None:
        q = select(Observation.source, Observation.entity_key, Observation.metric, Observation.obs_date,
                   Observation.value, Observation.snapshot_id)
        if sources:
            q = q.where(Observation.source.in_(sources))
        if since:
            q = q.where(Observation.obs_date >= since)
        df = pd.DataFrame(session.execute(q).all(),
                          columns=["source", "entity_key", "metric", "obs_date", "value", "snapshot_id"])
        self._series: dict[tuple, pd.Series] = {}
        if not df.empty:
            df["obs_date"] = pd.to_datetime(df["obs_date"])
            df["snapshot_id"] = df["snapshot_id"].fillna(0).astype(int)
            for key, g in df.groupby(["source", "entity_key", "metric", "snapshot_id"], sort=False):
                self._series[key] = g.set_index("obs_date")["value"].sort_index()
        snaps = session.execute(select(Snapshot.id, Snapshot.source, Snapshot.entity_key,
                                       Snapshot.window_start, Snapshot.window_end)).all()
        self._snapshots: dict[tuple[str, str], list] = {}
        for sid, src, key, ws, we in sorted(snaps, key=lambda r: (r[4], r[0])):
            self._snapshots.setdefault((src, key), []).append((sid, ws, we))

    def at(self, as_of: date) -> "AsOfView":
        return AsOfView(self, as_of)

    def pick_snapshot(self, source: str, entity_key: str, as_of: date) -> SeriesInfo | None:
        snaps = self._snapshots.get((source, entity_key))
        if not snaps:
            return None
        done = [s for s in snaps if s[2] <= as_of]
        if done:
            return SeriesInfo(done[-1][0], False)
        covering = [s for s in snaps if s[1] <= as_of <= s[2]]
        if covering:
            return SeriesInfo(min(covering, key=lambda s: (s[2], s[0]))[0], True)
        return None

    def raw(self, source: str, entity_key: str, metric: str, snapshot_id: int = 0) -> pd.Series:
        return self._series.get((source, entity_key, metric, snapshot_id), EMPTY)

    def has_snapshots(self, source: str) -> bool:
        return any(k[0] == source for k in self._snapshots)


class AsOfView:
    def __init__(self, repo: ObservationRepository, as_of: date) -> None:
        self.repo = repo
        self.as_of = as_of
        self._ts = pd.Timestamp(as_of)

    def series(self, source: str, entity_key: str, metric: str) -> tuple[pd.Series, SeriesInfo]:
        info = SeriesInfo()
        if self.repo.has_snapshots(source):
            picked = self.repo.pick_snapshot(source, entity_key, self.as_of)
            if picked is None:
                return EMPTY, info
            info = picked
            s = self.repo.raw(source, entity_key, metric, picked.snapshot_id)
        else:
            s = self.repo.raw(source, entity_key, metric)
        return s.loc[:self._ts], info

    def latest_value(self, source: str, entity_key: str, metric: str) -> tuple[float | None, date | None]:
        s, _ = self.series(source, entity_key, metric)
        if s.empty:
            return None, None
        return float(s.iloc[-1]), s.index[-1].date()

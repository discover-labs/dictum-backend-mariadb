from typing import List, Optional

from dictum_core.backends.mixins.datediff import DatediffCompilerMixin
from dictum_core.backends.secret import Secret
from dictum_core.backends.sql_alchemy import SQLAlchemyBackend, SQLAlchemyCompiler
from sqlalchemy import DateTime, Select, and_, cast, extract, func, literal, select


class MariaDBCompiler(DatediffCompilerMixin, SQLAlchemyCompiler):
    def datepart(self, part, arg):
        if part in {"dow", "dayofweek"}:
            return func.weekday(arg) + 1  # ISO week day (start Monday = 1)

        if part == "week":
            return func.week(arg, 3)  # mode 3 = ISO week number
        return extract(part, arg)

    def datetrunc(self, part, arg):
        if part == "year":
            return cast(func.date_format(arg, r"%Y-01-01 00:00:00"), DateTime)

        if part == "quarter":
            year = self.datetrunc("year", arg)
            quarter = func.quarter(arg)
            res = func.add_months(year, (quarter - 1) * 3)
            return cast(func.date_format(res, r"%Y-%m-01 00:00:00"), DateTime)

        if part == "month":
            return cast(func.date_format(arg, r"%Y-%m-01 00:00:00"), DateTime)

        if part == "week":
            wd = func.weekday(arg)
            res = func.adddate(arg, -wd)
            return cast(func.date_format(res, r"%Y-%m-%d 00:00:00"), DateTime)

        if part == "day":
            return cast(func.date_format(arg, r"%Y-%m-%d 00:00:00"), DateTime)

        if part == "hour":
            return cast(func.date_format(arg, r"%Y-%m-%d %H:00:00"), DateTime)

        if part == "minute":
            return cast(func.date_format(arg, r"%Y-%m-%d %H:%i:00"), DateTime)

        if part == "second":
            return cast(func.date_format(arg, r"%Y-%m-%d %H:%i:%s"), DateTime)

        raise NotImplementedError(f"Unsupported datepart: {part}")

    def datediff_day(self, start, end):
        """MariaDB datediff works only for days, so we use the standard mixin."""
        return func.datediff(end, start)


class MariaDBBackend(SQLAlchemyBackend):
    type = "mariadb"
    compiler_cls = MariaDBCompiler

    def __init__(
        self,
        database: Optional[str] = None,
        host: str = "localhost",
        port: int = 3306,
        username: str = "root",
        password: Secret = None,
        pool_size: Optional[int] = 5,
        default_schema: Optional[str] = None,
    ):
        super().__init__(
            drivername="mariadb+pymysql",
            database=database,
            host=host,
            port=port,
            username=username,
            password=password,
            pool_size=pool_size,
            default_schema=default_schema,
        )

    def union_all_full_outer_join(
        self, left: Select, right: Select, on: List[str], left_join: bool = False
    ) -> Select:
        """Perform a full outer join on two tables using UNION ALL of two LEFT JOINs
        or just a left join. Merge "on" columns with COALESCE.
        """
        on_columns = (
            set(left.selected_columns.keys())
            & set(right.selected_columns.keys())
            & set(on)
        )

        left = left.subquery()
        right = right.subquery()

        onclause = literal(True)
        if len(on_columns) > 0:
            onclause = and_(*(left.c[c] == right.c[c] for c in on_columns))

        # on_columns: columns that should be coalesce'd
        # other columns: left alone in both
        coalesced_columns = [
            func.coalesce(left.c[name], right.c[name]).label(name)
            for name in on_columns
        ]
        other_left_columns = [c for c in left.c if c.name not in on_columns]
        other_right_columns = [c for c in right.c if c.name not in on_columns]
        other_columns = [*other_left_columns, *other_right_columns]

        first: Select = select(*coalesced_columns, *other_columns).select_from(
            left.join(right, onclause=onclause, isouter=True)
        )

        if left_join:
            return first

        join_check = list(left.c)[-1]  # last column is the metric
        second = (
            select(*coalesced_columns, *other_columns)
            .select_from(right.join(left, onclause=onclause, isouter=True))
            .where(join_check == None)  # noqa: E711
        )
        return first.union_all(second)

    def merge_queries(self, bases: List[Select], on: List[str]):
        """MariaDB doesn't support full outer join, so we have to emulate it with
        UNION ALL and LEFT JOIN
        """
        # materialize bases that aren't materialized yet
        result, *rest = bases
        for add in rest:
            result = self.union_all_full_outer_join(result, add, on)
        return result.subquery().select()

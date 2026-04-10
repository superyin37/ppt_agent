from pydantic import BaseModel
from typing import Optional
from tool._base import ToolError


class ComputeFARInput(BaseModel):
    gross_floor_area: Optional[float] = None
    site_area: Optional[float] = None
    far: Optional[float] = None


class ComputeFAROutput(BaseModel):
    gross_floor_area: float
    site_area: float
    far: float
    computed_field: str     # 哪个字段是计算得出的


def compute_far_metrics(input: ComputeFARInput) -> ComputeFAROutput:
    """
    根据建筑面积、用地面积、容积率三者中的任意两个，计算第三个。
    至少需要提供两个值，否则抛出 ToolError。
    timeout: 0.1s
    """
    gfa = input.gross_floor_area
    sa = input.site_area
    far = input.far

    if gfa is not None and sa is not None:
        return ComputeFAROutput(
            gross_floor_area=gfa,
            site_area=sa,
            far=round(gfa / sa, 3),
            computed_field="far",
        )

    if gfa is not None and far is not None:
        computed_sa = round(gfa / far, 2)
        return ComputeFAROutput(
            gross_floor_area=gfa,
            site_area=computed_sa,
            far=far,
            computed_field="site_area",
        )

    if sa is not None and far is not None:
        computed_gfa = round(sa * far, 2)
        return ComputeFAROutput(
            gross_floor_area=computed_gfa,
            site_area=sa,
            far=far,
            computed_field="gross_floor_area",
        )

    raise ToolError(
        code="INSUFFICIENT_METRICS",
        message="至少需要两个指标（建筑面积、用地面积、容积率）才能计算",
        retryable=False,
    )

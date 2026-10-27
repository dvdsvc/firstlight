"""Source-backed profile cards for the geochronology specialist tools.

The cards intentionally keep a small semantic skeleton for a model call while
preserving the canonical USGS field spellings.  `discover` uses the first
field group; `enrich_candidates` can additionally use the completion group.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


USGS_TEMPLATE_RELEASE = {
    "title": "USGS Geochron: Data Compilation Templates (2.0, June 2025)",
    "doi": "10.5066/P14SSWBH",
    "url": "https://doi.org/10.5066/P14SSWBH",
    "dictionary": (
        "https://www.sciencebase.gov/catalog/file/get/"
        "6787f406d34e60ddd4de2996?f=__disk__31%2F67%2Fe8%2F"
        "3167e8f782c8cf5e50c74116b8268730fc92d69d"
    ),
}


# These fields recur across the USGS summary-template sheets.  They form the
# sample-property branch, not a separate global extraction schema.
COMMON_SAMPLE_FIELDS = (
    "SampleDesc",
    "IGSN",
    "FieldName",
    "GeologicalUnit",
    "Collector",
    "DateCollected",
    "SampleComments",
    "Detrital",
    "DepoAge",
    "DepoAgeUnc",
    "DepoAgeMax",
    "DepoAgeMin",
    "DepoAgeName",
    "DepoAgeNameMax",
    "DepoAgeNameMin",
    "SampleType",
    "SampleSrc",
    "CollectMethod",
    "RockClass",
    "Material",
    "Lat",
    "Long",
    "GeoDatum",
    "Depth",
    "Elevation",
    "Country",
    "StateProvince",
    "Quadrangle",
    "Locality",
    "LocalityDesc",
    "LocalityComment",
    "LocPrec",
    "LocPrecType",
    "LocPrecComment",
)

COMMON_METHOD_FIELDS = ("SampleMaterial", "Lab", "InstrumentMethod", "Analyst")
COMMON_AGGREGATE_FIELDS = (
    "Age_Text",
    "AgeUnc_Text",
    "AgeIntpnType",
    "AnalysisType",
    "NofAnalyses",
    "MSWD",
    "ProbFIt",
    "InclAnalysisAgeCalc",
)
COMMON_INFERENCE_FIELDS = ("AgeIntpnClass", "AgeIntprtdDesc", "AgeComments")


@dataclass(frozen=True)
class ProfileSpec:
    """One profile nested inside a method-specific MCP boundary."""

    profile_id: str
    mcp_server: str
    tool_id: str
    isotope_system: str
    techniques: tuple[str, ...]
    description: str
    template: str
    raw_unit_types: tuple[str, ...]
    route_signals: tuple[str, ...]
    technique_signals: tuple[str, ...]
    skeleton_raw_fields: tuple[str, ...]
    completion_raw_fields: tuple[str, ...]
    skeleton_aggregate_fields: tuple[str, ...]
    completion_aggregate_fields: tuple[str, ...]
    inference_fields: tuple[str, ...] = COMMON_INFERENCE_FIELDS

    @property
    def all_raw_fields(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.skeleton_raw_fields + self.completion_raw_fields))

    @property
    def all_aggregate_fields(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(self.skeleton_aggregate_fields + self.completion_aggregate_fields)
        )

    @property
    def allowed_method_fields(self) -> tuple[str, ...]:
        return COMMON_METHOD_FIELDS + ("isotope_system", "technique", "scope")

    def fields_for(self, operation: str) -> dict[str, tuple[str, ...]]:
        if operation not in {"discover", "enrich_candidates"}:
            raise ValueError(f"unsupported profile operation: {operation}")
        raw_fields = self.skeleton_raw_fields
        aggregate_fields = self.skeleton_aggregate_fields
        if operation == "enrich_candidates":
            raw_fields = self.all_raw_fields
            aggregate_fields = self.all_aggregate_fields
        return {
            "sample_attributes": COMMON_SAMPLE_FIELDS,
            "method_context": self.allowed_method_fields,
            "raw_observations": raw_fields,
            "aggregate_observations": aggregate_fields,
            "author_inferences": self.inference_fields,
        }


def _fields(values: str) -> tuple[str, ...]:
    return tuple(field for field in values.split() if field)


# Each name below is copied from the USGS 2.0 master data dictionary.  The
# cards are intentionally selective: papers rarely expose every laboratory
# correction term, while the second operation exposes the method-specific
# standard fields that matter when a candidate already exists.
PROFILE_SPECS: tuple[ProfileSpec, ...] = (
    ProfileSpec(
        profile_id="upb_in_situ",
        mcp_server="geochron_upb",
        tool_id="geochron_upb.extract_in_situ_delta",
        isotope_system="U-Pb",
        techniques=("LA-ICP-MS", "SIMS", "SHRIMP", "unknown"),
        description="U-Th-Pb 原位分析；优先 LA-ICP-MS，兼容 SIMS/SHRIMP spot 或 domain 工作流。",
        template="U-Th-Pb_insitu_Template.xlsx",
        raw_unit_types=("spot", "grain", "domain"),
        route_signals=("u-pb", "u–pb", "u—pb", "铀铅", "206pb/238u", "207pb/206pb"),
        technique_signals=(
            "la-icp-ms", "la-icpms", "laser ablation", "激光剥蚀", "激光烧蚀",
            "sims", "shrimp", "ion microprobe", "离子探针", "分析点", "测点",
        ),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel MountID LabRunID DateAnalyzed U Th Pb UTh ThU "
            "Pb206U238 Pb207U235 Pb207Pb206 Pb208Th232 Pb206U238Age Pb207U235Age "
            "Pb207Pb206Age PctDiscordW PctDiscordTW PctConcord DomainAnalyzed "
            "DomainDescript InclAnalysisAgeCalc"
        ),
        completion_raw_fields=_fields(
            "Pb206Pb204 Pb208Pb204 PctCommon206Pb Pb207CorrPctCommon206Pb "
            "Pb204CorrPb206U238 Pb207CorrPb206U238 Pb204CorrPb207U235 "
            "Pb204CorrPb207Pb206 RHOWetherill RHOTeraWasserburg ErrorCorrelation "
            "FracFactor LongExVar Hf176Hf177 Lu176Hf177 Yb176Hf177 d18O"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUnc1S_Text AgeIntpnType AnalysisType NofAnalyses "
            "MSWD ProbFIt"
        ),
        completion_aggregate_fields=_fields("AgeUncMin_Text AgeUncMax_Text"),
    ),
    ProfileSpec(
        profile_id="upb_id_tims",
        mcp_server="geochron_upb",
        tool_id="geochron_upb.extract_id_tims_delta",
        isotope_system="U-Pb",
        techniques=("ID-TIMS", "CA-ID-TIMS", "TIMS", "unknown"),
        description="U-Th-Pb 溶液/ID-TIMS 与 CA-ID-TIMS fraction 工作流。",
        template="U-Th-Pb_TIMS_Template.xlsx",
        raw_unit_types=("fraction", "aliquot", "grain"),
        route_signals=("u-pb", "u–pb", "u—pb", "铀铅", "isotope dilution", "同位素稀释"),
        technique_signals=(
            "id-tims", "ca-id-tims", "thermal ionization", "chemical abrasion", "tracer",
            "spike", "pb blank", "热电离", "化学磨蚀", "同位素稀释",
        ),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel U_ID Pb_ID TotGrains DateAnalyzed Weight U UUnc Th ThUnc "
            "Pb PbUnc ThU CommonPb Pb204Pct Pb206Pct Pb207Pct Pb208Pct CommonLeadModel "
            "DisequilCorrMethod ThUMagma Pb206U238Age Pb206U238AgeUnc2s Pb207U235Age "
            "Pb207U235AgeUnc2s Pb207Pb206Age Pb207Pb206AgeUnc2s PctDiscordW"
        ),
        completion_raw_fields=_fields(
            "Pb206Pb204Measured Pb208Pb206Measured Th232U238Measured U238DecayConst "
            "U235DecayConst Th232DecayConst CommonPbMass RadPbMass RadPbToCommonPb "
            "TotUMass U238U235 CorrCoef FracMass Pb206U238CorrSpike Pb206U238CorrBlank "
            "Pb207U235CorrSpike Pb207U235CorrBlank Pb204Pb206CorrSpike Pb204Pb206CorrBlank"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUnc2sTracer AgeUnc2sTracerDecay AgeIntpnType "
            "AnalysisType NofAnalyses MSWD"
        ),
        completion_aggregate_fields=_fields("AgeUncMin_Text AgeUncMax_Text"),
    ),
    ProfileSpec(
        profile_id="arar_incremental_heating",
        mcp_server="geochron_arar",
        tool_id="geochron_arar.extract_incremental_heating_delta",
        isotope_system="40Ar/39Ar",
        techniques=("incremental_heating", "step_heating", "unknown"),
        description="40Ar/39Ar 增量加热/阶段加热 profile。",
        template="Ar40-Ar39_Template.xlsx",
        raw_unit_types=("heating_step", "aliquot", "grain"),
        route_signals=("40ar/39ar", "40ar-39ar", "ar-ar", "氩氩"),
        technique_signals=("incremental heating", "step heating", "heating step", "坪年龄", "阶段加热"),
        skeleton_raw_fields=_fields(
            "Argon_ID Irrad_ID ParentRel Temperature Ar40 Ar40Unc Ar39 Ar39Unc Ar38 Ar38Unc "
            "Ar37 Ar37Unc Ar36 Ar36Unc Ar40rad Ar39perc Ar40RadAr39K Ar40RadAr39KUnc "
            "InitRatioAr4036 InitRatioAr4036Unc CaKratio CaKratioUnc KCaratio KCaratioUnc "
            "ClKratio ClKratioUnc KClratio KClratioUnc"
        ),
        completion_raw_fields=_fields(
            "Isoch3640 Isoch3640Unc Isoch3940 Isoch3940Unc Isoch3936 Isoch3936Unc "
            "Correl4039 Correl3639 DecayConstTotal DecayContTotalUnc DecayConstElctrnCapture "
            "DecayConstElctrnCptrunc DecayConstBeta DecayConstBetaUnc JValueAbs JValuePct JValueUnc"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUncInt AgeUncExt AgeIntpnType AnalysisType MSWD NofAnalyses"
        ),
        completion_aggregate_fields=_fields("AgeIntprtdDesc"),
    ),
    ProfileSpec(
        profile_id="arar_fusion",
        mcp_server="geochron_arar",
        tool_id="geochron_arar.extract_fusion_delta",
        isotope_system="40Ar/39Ar",
        techniques=("total_fusion", "single_grain_fusion", "laser_fusion", "unknown"),
        description="40Ar/39Ar 全熔融、激光熔融与单晶粒熔融 profile。",
        template="Ar40-Ar39_Template.xlsx",
        raw_unit_types=("grain", "aliquot", "fusion"),
        route_signals=("40ar/39ar", "40ar-39ar", "ar-ar", "氩氩"),
        technique_signals=("total fusion", "single grain fusion", "laser fusion", "全熔融", "单颗粒熔融", "激光熔融"),
        skeleton_raw_fields=_fields(
            "Argon_ID Irrad_ID ParentRel LaserPower Ar40 Ar40Unc Ar39 Ar39Unc Ar38 Ar38Unc "
            "Ar37 Ar37Unc Ar36 Ar36Unc Ar40rad Ar40RadAr39K Ar40RadAr39KUnc InitRatioAr4036"
        ),
        completion_raw_fields=_fields(
            "InitRatioAr4036Unc CaKratio CaKratioUnc KCaratio KCaratioUnc ClKratio ClKratioUnc "
            "KClratio KClratioUnc JValueAbs JValuePct JValueUnc"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUncInt AgeUncExt AgeIntpnType AnalysisType MSWD NofAnalyses"
        ),
        completion_aggregate_fields=_fields("AgeIntprtdDesc"),
    ),
    ProfileSpec(
        profile_id="k_ar",
        mcp_server="geochron_kar",
        tool_id="geochron_kar.extract_delta",
        isotope_system="K-Ar",
        techniques=("K-Ar", "unknown"),
        description="K-Ar profile。",
        template="K-Ar_One_Sheet_Template",
        raw_unit_types=("aliquot", "grain", "bulk"),
        route_signals=("k-ar", "k/ar", "钾氩"),
        technique_signals=("k-ar", "钾氩"),
        skeleton_raw_fields=_fields(
            "K_Id Ar_Id ParentRel K2OWtPct K2OWtPctUnc K2OWtPctNum K2OWtPctMethod "
            "ConcRad40 ConcRad40Unc PctRadAr40 Ar40Ar38 Ar38Ar36 Ar40K40 K40K"
        ),
        completion_raw_fields=_fields(
            "DecayConstTotal DecayContTotalUnc DecayConstElctrnCapture DecayConstElctrnCptrunc "
            "DecayConstBeta DecayConstBetaUnc DecayConstRef"
        ),
        skeleton_aggregate_fields=_fields("Age_Text AgeUnc_Text AgeIntpnType AnalysisType Analyses MSWD"),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="u_th_he",
        mcp_server="geochron_u_th_he",
        tool_id="geochron_u_th_he.extract_delta",
        isotope_system="(U-Th)/He",
        techniques=("single_grain", "multigrain_aliquot", "LADD", "unknown"),
        description="(U-Th)/He 单晶粒、multi-grain aliquot 与 laser-ablation He profile。",
        template="U-Th-He_Template.xlsx",
        raw_unit_types=("grain", "aliquot"),
        route_signals=("(u-th)/he", "u-th/he", "u-th-he", "u/th-he", "低温热年代学"),
        technique_signals=("single grain", "multigrain", "aliquot", "ladd", "laser ablation he"),
        skeleton_raw_fields=_fields(
            "UThHe_id ParentRel DateAnalyzed U UUnc Th ThUnc Sm SmUnc He HeUnc ThU eU eUUnc "
            "Mass TotGrains GrainGeometry L1 L2 W1 W2 T1 T2 ESR NPyramid Beta FT FTUnc "
            "UncorAge UncorAgeUnc InclAnalysisAgeCalc"
        ),
        completion_raw_fields=_fields(
            "FTU_235 FTU_238 FTU FTTh FTSm FZAC FZACUnc DeltaRimCore D230 UThPit UThPitUnc "
            "HePit HePitUnc Ung UngUnc Thng ThngUnc Smng SmngUnc Hencc HeUncncc"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeIntpnType AnalysisType FTRef NofAnalyses MSWD ProbFIt"
        ),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="u_series_in_situ",
        mcp_server="geochron_u_series",
        tool_id="geochron_u_series.extract_in_situ_delta",
        isotope_system="U-series",
        techniques=("in_situ", "LA-ICP-MS", "SIMS", "unknown"),
        description="U-series 原位分析 profile。",
        template="U-series_insitu_Template.xlsx",
        raw_unit_types=("spot", "domain", "grain"),
        route_signals=("u-series", "u series", "铀系", "230th/238u", "234u/238u"),
        technique_signals=("in situ", "la-icp-ms", "sims", "spot", "原位"),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel DateAnalyzed U Th UTh ThU ThUMagma ActRt230Th232Th "
            "ActRt238U232Th ActRt232Th238U ActRt230Th238U ActRt234U238U "
            "ActRtTh230u238CorrDetritus ActRtu234u238CorrDetritus DomainAnalyzed DomainDescript "
            "InclAnalysisAgeCalc"
        ),
        completion_raw_fields=_fields(
            "CorrActRt230Th232Th CorrActRt238U232Th ActRt254UO238U ActRt254UO248ThO "
            "ActRt248ThO254UO ActRt248ThO232Th ActRt246ThO248ThO ActRt246ThO254UO "
            "USeriesAnalyticComments"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUnc1s AgeUncMin1s AgeUncMax1s AgeIntpnType AnalysisType "
            "NofAnalyses MSWD ProbFIt"
        ),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="u_series_solution",
        mcp_server="geochron_u_series",
        tool_id="geochron_u_series.extract_solution_delta",
        isotope_system="U-series",
        techniques=("solution", "MC-ICP-MS", "TIMS", "unknown"),
        description="U-series 溶液分析 profile。",
        template="U-series_Solution_Template.xlsx",
        raw_unit_types=("aliquot", "fraction", "solution"),
        route_signals=("u-series", "u series", "铀系", "230th/238u", "234u/238u"),
        technique_signals=("solution", "mc-icp-ms", "tims", "dissolution", "溶液"),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel DateAnalyzed U UUnc Th ThUnc UTh ThU ActRt238U232Th "
            "ActRt230Th232Th ActRt232Th238U ActRt230Th238U ActRt234U238U ActRt230Th238UCorr "
            "InitActRt234U238U ActRt232Th238UDet ActRt230Th238UDet ActRt234U238UDet "
            "InclAnalysisAgeCalc"
        ),
        completion_raw_fields=_fields(
            "DecayConstRef234U230Th DecayConstRef238U DecayConstRef232Th CalculationComments "
            "USeriesAnalyticComments"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUncMin AgeUncMax AgeIntpnType AnalysisType NofAnalyses MSWD ProbFIt"
        ),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="fission_track",
        mcp_server="geochron_fission_track",
        tool_id="geochron_fission_track.extract_delta",
        isotope_system="Fission Track",
        techniques=("external_detector", "LA_ICP_MS", "unknown"),
        description="裂变径迹 profile。",
        template="Fission_Track_Template.xlsx",
        raw_unit_types=("grain", "mount", "analysis"),
        route_signals=("fission track", "裂变径迹", "ft age"),
        technique_signals=("external detector", "zeta", "track density", "径迹密度"),
        skeleton_raw_fields=_fields(
            "Analysis_ID MountID LabRunID ParentRel DateAnalyzed Zeta ZetaUnc TotGrains Area AreaUnit "
            "SpontaneousTrackDensity NumberSpontTracksCount InducedTrackDensity NumberInducedTracksCount "
            "TrackRatio TrackDensityInMsDetector NumDectectorTracks ExternalDetect ChiSquared "
            "MeanTrackLength MeanTrackLengthUnc NumTrackLengths TrackSTDev Dpar Dper U UUnc Th ThUnc"
        ),
        completion_raw_fields=_fields(
            "SpontDosimeterTrackDensity NumberSpontDosimeterTracksCount DosimeterGlass PValueChiSq "
            "NeutronFlux Sm SmUnc U238Ca43 U238Ca43Unc InclAnalysisAgeCalc"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUncMin_Text AgeUncMax_Text AgeIntpnType AnalysisType"
        ),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="cosmogenic_be10_al26",
        mcp_server="geochron_cosmogenic",
        tool_id="geochron_cosmogenic.extract_be10_al26_delta",
        isotope_system="Cosmogenic 10Be/26Al",
        techniques=("AMS", "unknown"),
        description="宇生核素 10Be/26Al profile。",
        template="Be10-Al26_One_Sheet_Template.xlsx",
        raw_unit_types=("aliquot", "mineral_separate", "sample"),
        route_signals=("10be", "26al", "be-10", "al-26", "cosmogenic", "宇生核素"),
        technique_signals=("ams", "accelerator mass spectrometry", "加速器质谱"),
        skeleton_raw_fields=_fields(
            "ParentRel Aliquot_Id YearCollected Mass Shielding Thickness Density PressureFlag SLHL ScalingRef "
            "InclAnalysisAgeCalc Be BeUnc lab_Be10_id DateAnalyzed_Be10 Be10 Be10Unc SubtractedBe10 "
            "SubtractedBe10Unc Be10_std Be9_Added Be10Be9 Be10Be9Unc Al AlUnc lab_Al26_id DateAnalyzed_Al26 "
            "Al26 Al26Unc SubtractedAl26 SubtractedAl26Unc Al26_std Al27 Al26Al27 Al26Al27Unc Al26Be10 Al26Be10Unc"
        ),
        completion_raw_fields=_fields(
            "Be_Age_0mmkyr Be_Age_0mmkyrUnc Be_Age_0mmkyrUncInt Be_Age_0mmkyrUncExt "
            "Al_Age_0mmkyr Al_Age_0mmkyrUnc Al_Age_0mmkyrUncInt Al_Age_0mmkyrUncExt "
            "ICED_Sample_Id ICED_Be10Al26_Id ICED_Age ICED_AgeUnc ICED_Age_CalcMethod"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUncInt AgeUncExt E_Rate E_RateUnc AgeIntpnType AnalysisType MSWD NofAnalyses"
        ),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="cosmogenic_he3",
        mcp_server="geochron_cosmogenic",
        tool_id="geochron_cosmogenic.extract_he3_delta",
        isotope_system="Cosmogenic 3He",
        techniques=("noble_gas_mass_spectrometry", "unknown"),
        description="宇生核素 3He profile。",
        template="He3_One_Sheet_Template.xlsx",
        raw_unit_types=("aliquot", "mineral_separate", "sample"),
        route_signals=("3he", "he-3", "cosmogenic", "宇生核素"),
        technique_signals=("noble gas", "mass spectrometry", "稀有气体"),
        skeleton_raw_fields=_fields(
            "ParentRel Aliquot_Id YearCollected Mass Shielding Thickness Density PressureFlag SLHL ScalingRef "
            "InclAnalysisAgeCalc He HeUnc lab_He3_id DateAnalyzed He3 He3Unc SubtractedHe3 SubtractedHe3Unc "
            "He3_std He4_Added He3He4 He3He4Unc"
        ),
        completion_raw_fields=_fields(
            "He_Age_0mmkyr He_Age_0mmkyrUnc He_Age_0mmkyrUncInt He_Age_0mmkyrUncExt "
            "ICED_Sample_Id ICED_He3_Id ICED_Age ICED_AgeUnc ICED_Age_CalcMethod"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeUncInt AgeUncExt E_Rate E_RateUnc AgeIntpnType AnalysisType MSWD NofAnalyses"
        ),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="radiocarbon_c14",
        mcp_server="geochron_radiocarbon",
        tool_id="geochron_radiocarbon.extract_delta",
        isotope_system="Radiocarbon",
        techniques=("AMS", "beta_counting", "unknown"),
        description="Radiocarbon / C14 profile。",
        template="C14_One_Sheet_Template.xlsx",
        raw_unit_types=("aliquot", "sample", "material"),
        route_signals=("radiocarbon", "14c", "c-14", "碳十四", "放射性碳"),
        technique_signals=("ams", "beta counting", "加速器质谱"),
        skeleton_raw_fields=_fields(
            "C14_ID Analysis_ID ParentRel UncalibAge_Text UncalibAgeUnc_Text UncalibAge UncalibAgeUnc "
            "CalibAge_Text CalibAgeUnc_Text CalibAge CalibAgeUnc CalibAgeCurveRef CalibAgeSoftware "
            "CalendarAge CalendarAgeUnc MinCalendarAge MaxCalendarAge MedianCalibAge_Text "
            "MinCalibAge_Text MaxCalibAge_Text SamplePrep HalfLife F14C F14CUnc D13C"
        ),
        completion_raw_fields=_fields(
            "UncalibAgeComment CalibAgeComment CalendarAgeComment CalculationComment "
            "CalendarAgeMinMaxInt CalibAgemMinMaxInt"
        ),
        skeleton_aggregate_fields=_fields(
            "CalibAge_Text CalibAgeUnc_Text CalendarAge CalendarAgeUnc AgeIntpnType AnalysisType"
        ),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="luminescence",
        mcp_server="geochron_luminescence",
        tool_id="geochron_luminescence.extract_delta",
        isotope_system="Luminescence",
        techniques=("OSL", "IRSL", "TL", "unknown"),
        description="OSL/IRSL/TL 光释光 profile。",
        template="Luminescence_Template",
        raw_unit_types=("aliquot", "grain", "sample"),
        route_signals=("osl", "irsl", "luminescence", "optically stimulated", "光释光", "释光"),
        technique_signals=("osl", "irsl", "tl", "single aliquot", "sar"),
        skeleton_raw_fields=_fields(
            "Analysis_ID Lum_ID ParentRel DateAnalyzed FieldMoisture SaturationMoisture WaterContentPreferred "
            "WaterContentPreferredError KPct KPctUnc U UUnc Th ThUnc Rb RbUnc CosmicDoseRate CosmicDoseRateUnc "
            "DoseRate DoseRateUnc GrainSizeMin GrainSizeMax AgeModelUsed AliquotsPassed AliquotsTotal "
            "EquivDose EquivDoseUnc1s EquivDoseScatter"
        ),
        completion_raw_fields=_fields(
            "TotalDoseRate TotalDoseRateUnc1s EquivDoseCAM EquivDoseCAM2s EquivDoseMAM EquivDoseMAM2s "
            "MAMAge_Text MAMAgeUnc_Text CAMAge_Text CAMAgeUnc_Text MeanAge_Text MeanAgeUnc_Text "
            "FadeRate FadeRateUnc FadeCAMAge_Text FadeCAMAgeUnc_Text FadeMAMAge_Text FadeMAMAgeUnc_Text"
        ),
        skeleton_aggregate_fields=_fields(
            "Age_Text AgeUnc_Text AgeIntpnType AnalysisType AgeModelUsed"
        ),
        completion_aggregate_fields=_fields("AgeQtz_Text AgeQtzUnc_Text AgeFld_Text AgeFldUnc_Text"),
    ),
    ProfileSpec(
        profile_id="rb_sr",
        mcp_server="geochron_rb_sr",
        tool_id="geochron_rb_sr.extract_delta",
        isotope_system="Rb-Sr",
        techniques=("TIMS", "MC-ICP-MS", "unknown"),
        description="Rb-Sr 同位素与等时线 profile。",
        template="Rb-Sr_Template.xlsx",
        raw_unit_types=("aliquot", "mineral_separate", "whole_rock"),
        route_signals=("rb-sr", "rb/sr", "87rb/86sr", "87sr/86sr", "铷锶"),
        technique_signals=("isochron", "等时线", "tims", "mc-icp-ms"),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel InitialSr87Sr86 InitialSr87Sr86Unc Sr87Sr86Calc Sr87Sr86CalcUnc "
            "Sr87Sr86Assumed Sr87Sr86AssumedUnc ConcentrationMethod Rb RbUnc Sr SrUnc Sr87rad "
            "Rb87Sr86Ratio Rb87Sr86RatioUnc Sr87Sr86Ratio Sr87Sr86RatioUnc AgeRb87Sr86 "
            "AgeRb87Sr86Unc AgeSr87Sr86 AgeSr87Sr86Unc"
        ),
        completion_raw_fields=_fields("SampleComments_RbSr MethodComments GeneralComments"),
        skeleton_aggregate_fields=_fields("Age_Text AgeUnc_Text AgeIntpnType AnalysisType"),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="sm_nd",
        mcp_server="geochron_sm_nd",
        tool_id="geochron_sm_nd.extract_delta",
        isotope_system="Sm-Nd",
        techniques=("TIMS", "MC-ICP-MS", "unknown"),
        description="Sm-Nd 同位素、epsilon Nd 与 model-age / isochron profile。",
        template="Sm-Nd_Template.xlsx",
        raw_unit_types=("aliquot", "mineral_separate", "whole_rock"),
        route_signals=("sm-nd", "sm/nd", "147sm/144nd", "143nd/144nd", "钐钕", "εnd", "end"),
        technique_signals=("isochron", "等时线", "tims", "mc-icp-ms"),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel Weight Sm SmUnc Nd NdUnc Nd143Nd144Calc Nd143Nd144CalcUnc "
            "Nd143Nd144Assumed Nd143Nd144AssumedUnc Nd143Nd144Measured Nd143Nd144MeasuredUnc "
            "Sm147Nd144Measured Sm147Nd144MeasuredUnc eNd_t Tdm Tdm_Text TdmModel "
            "ConcentrationMethod AgeSm147Nd144 AgeSm147Nd144Unc AgeNd143Nd144 AgeNd143Nd144Unc"
        ),
        completion_raw_fields=_fields("SampleComments_SmNd MethodComments GeneralComments"),
        skeleton_aggregate_fields=_fields("Age_Text AgeUnc_Text AgeIntpnType AnalysisType MSWD NofAnalyses"),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="lu_hf",
        mcp_server="geochron_lu_hf",
        tool_id="geochron_lu_hf.extract_delta",
        isotope_system="Lu-Hf",
        techniques=("LA-MC-ICP-MS", "MC-ICP-MS", "TIMS", "unknown"),
        description="Lu-Hf 同位素、epsilon Hf 与 model-age / isochron profile。",
        template="Lu-Hf_Template.xlsx",
        raw_unit_types=("spot", "grain", "aliquot", "whole_rock"),
        route_signals=("lu-hf", "lu/hf", "176lu/177hf", "176hf/177hf", "镥铪", "εhf", "ehf"),
        technique_signals=("la-mc-icp-ms", "mc-icp-ms", "tims", "laser ablation"),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel InitialHf176Hf177 InitialHf176Hf177Unc Hf176Hf177Calc "
            "Hf176Hf177CalcUnc Hf176Hf177Assumed Hf176Hf177AssumedUnc Lu LuUnc Hf HfUnc "
            "Hf176Hf177Measured Hf176Hf177MeasuredUnc Lu176Hf177Measured Lu176Hf177MeasuredUnc "
            "eHf_0 eHf_t Tdm Tdm_Text TdmModel Weight DecayConstRef"
        ),
        completion_raw_fields=_fields("SampleComments_LuHf MethodComments OtherComments"),
        skeleton_aggregate_fields=_fields("Age_Text AgeUnc_Text AgeIntpnType AnalysisType MSWD NofAnalyses"),
        completion_aggregate_fields=(),
    ),
    ProfileSpec(
        profile_id="re_os",
        mcp_server="geochron_re_os",
        tool_id="geochron_re_os.extract_delta",
        isotope_system="Re-Os",
        techniques=("ID-NTIMS", "MC-ICP-MS", "unknown"),
        description="Re-Os 同位素与等时线 profile。",
        template="Re-Os_Template.xlsx",
        raw_unit_types=("aliquot", "mineral_separate", "whole_rock"),
        route_signals=("re-os", "re/os", "187re/188os", "187os/188os", "铼锇"),
        technique_signals=("isochron", "等时线", "id-ntims", "mc-icp-ms"),
        skeleton_raw_fields=_fields(
            "Analysis_ID ParentRel Weight Re ReUnc Os OsUnc Re187 Re187Unc Os187 Os187Unc "
            "Os187Os188Calc Os187Os188CalcUnc Re187Os188 Re187Os188Unc Os187Os188 Os187Os188Unc "
            "Os187TotalOs CorrCoef Os192 Os192Unc ReBlankPct Os187BlankPct Os188BlankPct "
            "Os187RadPct Initial187Os188Os Initial187Os188OsUnc"
        ),
        completion_raw_fields=(),
        skeleton_aggregate_fields=_fields("Age_Text AgeUnc_Text AgeIntpnType AnalysisType MSWD NofAnalyses"),
        completion_aggregate_fields=(),
    ),
)


PROFILE_BY_ID = {spec.profile_id: spec for spec in PROFILE_SPECS}


def get_spec(profile_id: str) -> ProfileSpec:
    try:
        return PROFILE_BY_ID[profile_id]
    except KeyError as exc:
        known = ", ".join(sorted(PROFILE_BY_ID))
        raise ValueError(f"unknown profile {profile_id!r}; known profiles: {known}") from exc


def _render_fields(fields: tuple[str, ...]) -> str:
    return "、".join(fields) if fields else "本轮没有额外字段"


def build_delta_prompt(spec: ProfileSpec, operation: str) -> str:
    """Return the compact task prompt for one profile operation."""
    operation_text = (
        "建立当前 profile 的第一轮语义骨架：样品属性、原始观测、聚合观测和作者推理。原始观测"
        "作为结构索引，只保留直接支撑聚合结果或作者推理、且能在原文明确定位的必要记录；长表的"
        "逐行属性留给后续 enrich_candidates。"
        if operation == "discover"
        else "围绕 current_profile_state 已有节点或本轮修复上下文补充缺失的标准字段、证据或关系；"
        "保持已有树不复述。若当前状态为空，围绕修复上下文建立紧凑且可闭合的样品子树。"
    )
    return f"""
任务：{operation_text}

你是 {spec.description}。论文全文可见，用于核对跨段、表格、图注、方法和讨论的同一证据链；本工具只向
`profiles.{spec.profile_id}.samples` 提交增量。发现其他体系的证据时，将其作为 uncovered 报告，并带
suggested_profile_id；顶层 agent 再决定是否派发该工具。

输出以 sample_patch 保留自然树，不把四层内容平铺为 kind 列表：
sample_attributes → method_context → raw_observations → aggregate_observations → author_inferences。
method_context 的 isotope_system 为
{spec.isotope_system}，technique 从：{_render_fields(spec.techniques)} 中选择；scope 只使用 self 或 cited。

严格工具参数已经为每一层固定 JSON Schema。method_context 的 isotope_system、technique、scope 是独立 enum
字段；样品属性、其余方法字段和每个观测的 fields 使用 {{"name": "字段名", "value": 值}} 的 field_values
列表。只填本轮需要保存的信息，不重复摘录 evidence_text，也不逐项解释字段归属。
aggregate_observations 的 source_raw_observation_ids 引用同一 sample 已有或本次新增的原始观测；
author_inferences 的 aggregate_observation_ids 引用同一 sample
已有或本次新增的聚合观测。原文只给出样品级汇总结果时，聚合观测可保留空的 source_raw_observation_ids，
不要臆造点位关系。仅把作者明确赋予的地质意义写入作者推理层。
""".strip()


def _closed_object(properties: dict[str, Any]) -> dict[str, Any]:
    """Build the object shape required by DeepSeek strict tool mode."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_SCALAR_VALUE_SCHEMA: dict[str, Any] = {
    "anyOf": [
        {"type": "string"},
        {"type": "number"},
        {"type": "boolean"},
    ]
}


def _field_entry_schema() -> dict[str, Any]:
    return _closed_object(
        {
            "name": {"type": "string"},
            "value": _SCALAR_VALUE_SCHEMA,
        }
    )


def _method_context_schema(spec: ProfileSpec) -> dict[str, Any]:
    """Make profile identity mandatory instead of hiding it in a sparse field list."""
    return _closed_object(
        {
            "isotope_system": {"type": "string", "enum": [spec.isotope_system]},
            "technique": {"type": "string", "enum": list(spec.techniques)},
            "scope": {"type": "string", "enum": ["self", "cited"]},
            "field_values": {
                "type": "array",
                "items": _field_entry_schema(),
            },
        }
    )


def _finding_schema(kind: str) -> dict[str, Any]:
    return _closed_object(
        {
            "kind": {"type": "string", "enum": [kind]},
            "description": {"type": "string"},
            "suggested_profile_id": {
                "type": "string",
                "enum": ["", *sorted(PROFILE_BY_ID)],
            },
        }
    )


def delta_schema(profile_id: str, operation: str = "discover") -> dict[str, Any]:
    """Strict tool-call wire schema for one profile and one operation.

    The model receives this schema directly.  Fields use sparse ``{name, value}``
    arrays: the schema fixes tree shape and profile identity without turning the
    extraction call into a field-by-field evidence annotation task.
    """
    spec = get_spec(profile_id)
    field_entry = {
        "type": "array",
        "items": _field_entry_schema(),
    }
    raw_observation = _closed_object(
        {
            "id": {"type": "string"},
            "unit_type": {"type": "string"},
            "field_values": field_entry,
        }
    )
    aggregate_observation = _closed_object(
        {
            "id": {"type": "string"},
            "field_values": field_entry,
            "source_raw_observation_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )
    author_inference = _closed_object(
        {
            "id": {"type": "string"},
            "aggregate_observation_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "field_values": field_entry,
        }
    )
    sample_patch = _closed_object(
        {
            "sample_id": {"type": "string"},
            "sample_attributes": field_entry,
            "method_context": _method_context_schema(spec),
            "raw_observations": {"type": "array", "items": raw_observation},
            "aggregate_observations": {"type": "array", "items": aggregate_observation},
            "author_inferences": {"type": "array", "items": author_inference},
        }
    )
    return _closed_object(
        {
            "profile_id": {"type": "string", "enum": [profile_id]},
            "operation": {"type": "string", "enum": [operation]},
            "sample_patches": {"type": "array", "items": sample_patch},
            "conflicts": {"type": "array", "items": _finding_schema("conflict")},
            "uncovered": {"type": "array", "items": _finding_schema("uncovered")},
        }
    )


def _field_mapping(entries: Any, path: str) -> dict[str, Any]:
    if not isinstance(entries, list):
        raise ValueError(f"{path} must be an array")
    mapped: dict[str, Any] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}[{index}] must be an object")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{path}[{index}].name must be a non-empty string")
        if name in mapped:
            raise ValueError(f"{path} repeats field {name!r}")
        mapped[name] = entry.get("value")
    return mapped


def decode_delta_wire(spec: ProfileSpec, wire: dict[str, Any]) -> dict[str, Any]:
    """Convert strict tool arguments to the existing reducer-owned tree patch."""
    if not isinstance(wire, dict):
        raise ValueError("strict profile tool arguments must be an object")
    patches = wire.get("sample_patches")
    if not isinstance(patches, list):
        raise ValueError("sample_patches must be an array")
    decoded_patches: list[dict[str, Any]] = []
    for patch_index, patch in enumerate(patches):
        if not isinstance(patch, dict):
            raise ValueError(f"sample_patches[{patch_index}] must be an object")
        raw_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(patch.get("raw_observations") or []):
            if not isinstance(row, dict):
                raise ValueError(f"raw_observations[{row_index}] must be an object")
            raw_rows.append(
                {
                    "id": row.get("id"),
                    "unit_type": row.get("unit_type"),
                    "fields": _field_mapping(
                        row.get("field_values"),
                        f"sample_patches[{patch_index}].raw_observations[{row_index}].field_values",
                    ),
                }
            )
        aggregate_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(patch.get("aggregate_observations") or []):
            if not isinstance(row, dict):
                raise ValueError(f"aggregate_observations[{row_index}] must be an object")
            aggregate_rows.append(
                {
                    "id": row.get("id"),
                    "fields": _field_mapping(
                        row.get("field_values"),
                        f"sample_patches[{patch_index}].aggregate_observations[{row_index}].field_values",
                    ),
                    "source_raw_observation_ids": row.get("source_raw_observation_ids"),
                }
            )
        inference_rows: list[dict[str, Any]] = []
        for row_index, row in enumerate(patch.get("author_inferences") or []):
            if not isinstance(row, dict):
                raise ValueError(f"author_inferences[{row_index}] must be an object")
            inference_rows.append(
                {
                    "id": row.get("id"),
                    "aggregate_observation_ids": row.get("aggregate_observation_ids"),
                    "fields": _field_mapping(
                        row.get("field_values"),
                        f"sample_patches[{patch_index}].author_inferences[{row_index}].field_values",
                    ),
                }
            )
        decoded_patches.append(
            {
                "sample_id": patch.get("sample_id"),
                "sample_attributes_add": _field_mapping(
                    patch.get("sample_attributes"),
                    f"sample_patches[{patch_index}].sample_attributes",
                ),
                "method_context_add": {
                    **_field_mapping(
                        (patch.get("method_context") or {}).get("field_values"),
                        f"sample_patches[{patch_index}].method_context.field_values",
                    ),
                    "isotope_system": (patch.get("method_context") or {}).get("isotope_system"),
                    "technique": (patch.get("method_context") or {}).get("technique"),
                    "scope": (patch.get("method_context") or {}).get("scope"),
                },
                "raw_observations_add": raw_rows,
                "aggregate_observations_add": aggregate_rows,
                "author_inferences_add": inference_rows,
            }
        )
    return {
        "profile_id": wire.get("profile_id"),
        "operation": wire.get("operation"),
        "sample_patches": decoded_patches,
        "conflicts": wire.get("conflicts"),
        "uncovered": wire.get("uncovered"),
    }


def validate_delta(spec: ProfileSpec, delta: dict[str, Any]) -> dict[str, Any]:
    """Enforce method/profile ownership and standard field permissions."""
    errors: list[str] = []
    warnings: list[str] = []
    if delta.get("profile_id") != spec.profile_id:
        errors.append(f"profile_id must be {spec.profile_id!r}")
    operation = delta.get("operation")
    if operation not in {"discover", "enrich_candidates"}:
        errors.append("operation must be discover or enrich_candidates")
        operation = "discover"
    patches = delta.get("sample_patches")
    conflicts = delta.get("conflicts")
    uncovered = delta.get("uncovered")
    if not isinstance(patches, list):
        errors.append("sample_patches must be an array")
        patches = []
    if not isinstance(conflicts, list):
        errors.append("conflicts must be an array")
    if not isinstance(uncovered, list):
        errors.append("uncovered must be an array")

    seen_samples: set[str] = set()
    raw_count = aggregate_count = inference_count = 0

    for patch_index, patch in enumerate(patches):
        path = f"sample_patches[{patch_index}]"
        if not isinstance(patch, dict):
            errors.append(f"{path} must be an object")
            continue
        allowed_patch_keys = {
            "sample_id", "sample_attributes_add", "sample_evidence", "method_context_add",
            "method_evidence", "raw_observations_add", "aggregate_observations_add",
            "author_inferences_add",
        }
        unknown_patch_keys = set(patch) - allowed_patch_keys
        if unknown_patch_keys:
            errors.append(f"{path} has forbidden keys {sorted(unknown_patch_keys)}")
        sample_id = patch.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            errors.append(f"{path}.sample_id must be a non-empty string")
        elif sample_id in seen_samples:
            errors.append(f"duplicate sample patch: {sample_id}")
        else:
            seen_samples.add(sample_id)

        sample_attributes = patch.get("sample_attributes_add") or {}
        if not isinstance(sample_attributes, dict):
            errors.append(f"{path}.sample_attributes_add must be an object")

        context = patch.get("method_context_add") or {}
        if not isinstance(context, dict):
            errors.append(f"{path}.method_context_add must be an object")
            context = {}
        elif context:
            if context.get("isotope_system") != spec.isotope_system:
                errors.append(f"{path}.method_context_add.isotope_system must be {spec.isotope_system}")
            if context.get("technique") not in spec.techniques:
                errors.append(f"{path}.method_context_add.technique is outside profile")
            if context.get("scope") not in {"self", "cited"}:
                errors.append(f"{path}.method_context_add.scope must be self or cited")

        for row_index, row in enumerate(patch.get("raw_observations_add") or []):
            raw_count += 1
            row_path = f"{path}.raw_observations_add[{row_index}]"
            if not isinstance(row, dict):
                errors.append(f"{row_path} must be an object")
                continue
            fields = row.get("fields")
            if not isinstance(fields, dict):
                errors.append(f"{row_path}.fields must be an object")

        for row_index, row in enumerate(patch.get("aggregate_observations_add") or []):
            aggregate_count += 1
            row_path = f"{path}.aggregate_observations_add[{row_index}]"
            if not isinstance(row, dict):
                errors.append(f"{row_path} must be an object")
                continue
            fields = row.get("fields")
            if not isinstance(fields, dict):
                errors.append(f"{row_path}.fields must be an object")
            refs = row.get("source_raw_observation_ids")
            if not isinstance(refs, list):
                errors.append(f"{row_path}.source_raw_observation_ids must be an array")

        for row_index, row in enumerate(patch.get("author_inferences_add") or []):
            inference_count += 1
            row_path = f"{path}.author_inferences_add[{row_index}]"
            if not isinstance(row, dict):
                errors.append(f"{row_path} must be an object")
                continue
            fields = row.get("fields")
            if not isinstance(fields, dict):
                errors.append(f"{row_path}.fields must be an object")
            refs = row.get("aggregate_observation_ids")
            if not isinstance(refs, list) or not refs:
                warnings.append(f"{row_path} has no aggregate_observation_ids; reducer will reject it")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "sample_patches": len(patches),
            "raw_observations": raw_count,
            "aggregate_observations": aggregate_count,
            "author_inferences": inference_count,
            "conflicts": len(conflicts) if isinstance(conflicts, list) else 0,
            "uncovered": len(uncovered) if isinstance(uncovered, list) else 0,
        },
    }

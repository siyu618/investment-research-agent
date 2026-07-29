# Strategy module loader — handles hyphenated directory names
# Python cannot import "fundamental-analysis" directly, so we use importlib.

import importlib

_LOADED: dict[str, object] = {}

SKILL_MODULES: dict[str, str] = {
    "fundamental-analysis": "strategies.fundamental_analysis.analyzer",
    "valuation-analysis": "strategies.valuation_analysis.analyzer",
    "risk-analysis": "strategies.risk_analysis.analyzer",
    "technical-analysis": "strategies.technical_analysis.analyzer",
    "portfolio-selection": "strategies.portfolio_selection.analyzer",
}

SKILL_CLASSES: dict[str, str] = {
    "fundamental-analysis": "FundamentalAnalysisSkill",
    "valuation-analysis": "ValuationAnalysisSkill",
    "risk-analysis": "RiskAnalysisSkill",
    "technical-analysis": "TechnicalAnalysisSkill",
    "portfolio-selection": "PortfolioSelectionSkill",
}


def load_skill(skill_name: str, **kwargs) -> object:
    """Load a skill class by name, instantiating with given kwargs."""
    module_path = SKILL_MODULES.get(skill_name)
    class_name = SKILL_CLASSES.get(skill_name)
    if not module_path or not class_name:
        raise ImportError(f"Unknown skill: {skill_name}")

    # Convert hyphens to underscores for the actual Python path
    py_path = module_path.replace("-", "_")
    try:
        module = importlib.import_module(py_path)
    except ImportError:
        # Fallback: try the original hyphenated module
        module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**kwargs)

# New agents with tools (recommended)
from .borrower_profiler_new import BorrowerProfilerAgent
from .lender_matcher_new import LenderMatcherAgent
from .contract_generator_new import ContractGeneratorAgent
from .payment_monitor_new import PaymentMonitorAgent
from .dispute_resolver_new import DisputeResolverAgent

# Legacy agents (deprecated)
from .borrower_profiler import BorrowerProfilerAgent as BorrowerProfilerAgentLegacy
from .lender_matcher import LenderMatcherAgent as LenderMatcherAgentLegacy
from .contract_generator import ContractGeneratorAgent as ContractGeneratorAgentLegacy
from .payment_monitor import PaymentMonitorAgent as PaymentMonitorAgentLegacy
from .dispute_resolver import DisputeResolverAgent as DisputeResolverAgentLegacy

__all__ = [
    # New agents with tools
    "BorrowerProfilerAgent",
    "LenderMatcherAgent",
    "ContractGeneratorAgent",
    "PaymentMonitorAgent",
    "DisputeResolverAgent",
    # Legacy
    "BorrowerProfilerAgentLegacy",
    "LenderMatcherAgentLegacy",
    "ContractGeneratorAgentLegacy",
    "PaymentMonitorAgentLegacy",
    "DisputeResolverAgentLegacy",
]

"""Launch industry configs used by acquisition query expansion."""

LAUNCH_INDUSTRY_CONFIGS: dict[str, dict[str, list[str] | str]] = {
    "metal_fabrication": {
        "label": "Metal Fabrication",
        "query_templates": [
            "metal fabricator {location}",
            "welding workshop {location}",
            "gate fabricator {location}",
            "stainless steel fabricator {location}",
        ],
        "excluded_terms": [
            "scrap yard",
            "hardware store",
            "construction company",
            "steel distributor",
            "welding supply store",
            "general contractor",
            "steel mills",
            "industrial manufacturer",
        ],
        "target_terms": [
            "fabricator",
            "fabrication",
            "welding",
            "welder",
            "gate",
            "stainless steel",
            "steel fabricator",
        ],
        "large_business_terms": [
            "mills",
            "industries",
            "group",
            "factory",
            "distributor",
            "manufacturer",
            "contractors",
        ],
        "campaign_segment": "metal_fabrication_whatsapp_outbound",
        "recommended_offer": "WhatsApp quote-to-delivery workflow",
    },
    "furniture_woodwork": {
        "label": "Furniture and Woodwork",
        "query_templates": [
            "furniture workshop {location}",
            "woodwork workshop {location}",
            "carpenter {location}",
            "custom furniture {location}",
        ],
        "excluded_terms": [
            "mattress shop",
            "appliance store",
            "interior decor showroom",
            "furniture mall",
            "wholesaler",
        ],
        "target_terms": [
            "furniture",
            "woodwork",
            "woodworks",
            "carpenter",
            "cabinet",
            "joinery",
            "custom furniture",
        ],
        "large_business_terms": [
            "factory",
            "industries",
            "wholesaler",
            "distributor",
            "manufacturer",
        ],
        "campaign_segment": "furniture_woodwork_whatsapp_outbound",
        "recommended_offer": "WhatsApp inquiry-to-order workflow",
    },
}


def get_industry_config(industry_class: str) -> dict[str, list[str] | str]:
    """Return a launch industry config or raise a clear error."""
    try:
        return LAUNCH_INDUSTRY_CONFIGS[industry_class]
    except KeyError as exc:
        raise ValueError(f"Unsupported launch industry '{industry_class}'") from exc

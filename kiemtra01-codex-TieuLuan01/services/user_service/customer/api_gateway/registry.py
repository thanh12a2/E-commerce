import os

from .definitions import CODE_LOCATIONS, ROUTE_DEFINITIONS, ROUTE_SECTION_DEFINITIONS, SERVICE_DEFINITIONS


def _rstrip_slash(value):
    return (value or "").rstrip("/")


def _join_url(base_url, path):
    normalized_path = "/" + str(path or "").lstrip("/")
    return f"{_rstrip_slash(base_url)}{normalized_path}"


def _user_public_base(request=None):
    if request is not None:
        return _rstrip_slash(request.build_absolute_uri("/"))
    return "http://localhost:8000"


def _build_service_map(user_public_base):
    service_map = {}
    for definition in SERVICE_DEFINITIONS:
        if definition["key"] == "user_service":
            internal_url = user_public_base
            public_urls = (
                {"label": "Customer UI", "url": user_public_base},
                {"label": "Staff UI", "url": "http://localhost:8003"},
            )
        else:
            internal_url = _rstrip_slash(
                os.getenv(definition["internal_env"]) or definition["internal_default"]
            )
            public_urls = (
                {"label": "Public host", "url": definition["localhost"]},
            )

        service_map[definition["key"]] = {
            "key": definition["key"],
            "label": definition["label"],
            "role": definition["role"],
            "localhost": definition["localhost"],
            "public_urls": list(public_urls),
            "internal": internal_url,
            "notes": definition["notes"],
            "touchpoints": list(definition["touchpoints"]),
        }

    return service_map


def _build_routes(user_public_base, service_map):
    routes = []
    for definition in ROUTE_DEFINITIONS:
        public_urls = [_join_url(user_public_base, path) for path in definition["public_paths"]]
        upstream_service = service_map[definition["upstream"]]
        upstream_urls = [
            _join_url(upstream_service["internal"], path)
            for path in definition["upstream_paths"]
        ]
        routes.append(
            {
                "id": definition["id"],
                "section": definition["section"],
                "title": definition["title"],
                "consumer_surface": definition["consumer_surface"],
                "gateway": definition["gateway"],
                "methods": list(definition["methods"]),
                "method": "/".join(definition["methods"]),
                "public_paths": list(definition["public_paths"]),
                "public_path": " + ".join(definition["public_paths"]),
                "public_urls": public_urls,
                "public_url": public_urls[0],
                "upstream": definition["upstream"],
                "upstream_paths": list(definition["upstream_paths"]),
                "upstream_urls": upstream_urls,
                "description": definition["description"],
                "request_shape": definition["request_shape"],
                "response_shape": definition["response_shape"],
            }
        )
    return routes


def _build_sections(routes):
    section_lookup = {}
    for route in routes:
        section_lookup.setdefault(route["section"], []).append(route)

    sections = []
    for definition in ROUTE_SECTION_DEFINITIONS:
        section_routes = section_lookup.get(definition["key"], [])
        sections.append(
            {
                "key": definition["key"],
                "title": definition["title"],
                "summary": definition["summary"],
                "route_count": len(section_routes),
                "routes": section_routes,
            }
        )
    return sections


def build_gateway_registry(request=None):
    user_public_base = _user_public_base(request)
    service_map = _build_service_map(user_public_base)
    routes = _build_routes(user_public_base, service_map)
    sections = _build_sections(routes)
    downstream_services = {
        route["upstream"]
        for route in routes
        if route["upstream"] != "user_service"
    }
    public_entrypoints = sum(len(route["public_paths"]) for route in routes)

    return {
        "message": "Gateway API index",
        "gateway_index_url": _join_url(user_public_base, "/gateway/apis/"),
        "gateway_dashboard_url": _join_url(user_public_base, "/gateway/"),
        "services": service_map,
        "service_cards": list(service_map.values()),
        "routes": routes,
        "sections": sections,
        "stats": {
            "service_count": len(service_map),
            "section_count": len(sections),
            "route_count": len(routes),
            "downstream_count": len(downstream_services),
            "public_entrypoint_count": public_entrypoints,
        },
        "code_locations": list(CODE_LOCATIONS),
    }

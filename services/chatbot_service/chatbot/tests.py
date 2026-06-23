import csv
import io
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import Client, TestCase

from . import services
from .behavior_ai import predict_behavior_for_user_ref, record_behavior_event, train_and_save_behavior_model
from .behavior_graph import build_behavior_graph_payload
from .category_taxonomy import detect_category_matches
from .dataset_generation import CatalogProduct, DATASET_COLUMNS, OFFICIAL_BEHAVIOR_TYPES, write_behavior_dataset_bundle
from .models import BehaviorEvent
from .rag_kb import load_knowledge_base


RUNTIME_CATEGORIES = [
    {"slug": "business-laptops", "name": "Business Laptops"},
    {"slug": "gaming-laptops", "name": "Gaming Laptops"},
    {"slug": "ultrabooks", "name": "Ultrabooks"},
    {"slug": "smartphones", "name": "Smartphones"},
    {"slug": "tablets", "name": "Tablets"},
    {"slug": "smartwatches", "name": "Smartwatches"},
    {"slug": "audio", "name": "Audio"},
    {"slug": "keyboards-mice", "name": "Keyboards & Mice"},
    {"slug": "chargers-cables", "name": "Chargers & Cables"},
    {"slug": "bags-stands", "name": "Bags & Stands"},
]


def _json_response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def _dataset_catalog_fixture():
    price_map = {
        "business-laptops": ["1049.00", "1299.00", "1599.00"],
        "gaming-laptops": ["1849.00", "2099.00", "2399.00"],
        "ultrabooks": ["949.00", "1199.00", "1499.00"],
        "smartphones": ["649.00", "999.00", "1299.00"],
        "tablets": ["499.00", "749.00", "1199.00"],
        "smartwatches": ["249.00", "399.00", "699.00"],
        "audio": ["99.00", "199.00", "329.00"],
        "keyboards-mice": ["59.00", "109.00", "179.00"],
        "chargers-cables": ["19.00", "49.00", "99.00"],
        "bags-stands": ["39.00", "89.00", "189.00"],
    }
    products = []
    product_id = 1
    for category in RUNTIME_CATEGORIES:
        for variant, price in enumerate(price_map[category["slug"]], start=1):
            products.append(
                CatalogProduct(
                    product_id=product_id,
                    category_slug=category["slug"],
                    category_name=category["name"],
                    name=f"{category['name']} Demo {variant}",
                    brand=f"Brand {variant}",
                    price=Decimal(price),
                    stock=20 + variant,
                )
            )
            product_id += 1
    return products


class ChatbotTaxonomyTests(TestCase):
    def test_detect_category_matches_understands_runtime_taxonomy(self):
        matches = detect_category_matches(
            "Need a business laptop plus a compact charger for travel.",
            categories=RUNTIME_CATEGORIES,
        )
        self.assertIn("business-laptops", matches)
        self.assertIn("chargers-cables", matches)

    def test_record_behavior_event_persists_category_slug(self):
        record_behavior_event(
            user_ref="7",
            message="Need accessories for travel.",
            current_product={"category_slug": "bags-stands", "id": 21},
            user_context={"cart_items": ["Commute Pack 16"], "saved_items": [], "recent_paid_items": []},
        )
        event = BehaviorEvent.objects.get()
        self.assertEqual(event.category_slug, "bags-stands")
        self.assertEqual(event.metadata["current_category_slug"], "bags-stands")

    def test_predict_behavior_prefers_question_and_history_categories(self):
        with patch("chatbot.behavior_ai.fetch_catalog_categories", return_value=RUNTIME_CATEGORIES):
            record_behavior_event(
                user_ref="42",
                message="I want wireless earbuds and good audio for commuting.",
                current_product={"category_slug": "audio", "id": 8},
                user_context={"cart_items": [], "saved_items": [], "recent_paid_items": []},
            )
            prediction = predict_behavior_for_user_ref(
                user_ref="42",
                question="Suggest more audio gear for meetings and travel.",
                current_product={"category_slug": "audio", "id": 8},
                user_context={"cart_items": ["QuietBeat ANC"], "saved_items": [], "recent_paid_items": []},
            )
        self.assertEqual(prediction["dominant_category_slug"], "audio")
        self.assertGreater(prediction["category_scores"]["audio"], 0)


class ChatbotArtifactTests(TestCase):
    def test_train_behavior_model_writes_dynamic_category_slug_artifacts(self):
        record_behavior_event(
            user_ref="audio-user",
            message="Need earbuds, speakers, and better audio for work calls.",
            current_product={"category_slug": "audio", "id": 7},
            user_context={"cart_items": ["QuietBeat ANC"], "saved_items": [], "recent_paid_items": []},
        )
        record_behavior_event(
            user_ref="travel-user",
            message="Looking for a travel bag and a desk stand.",
            current_product={"category_slug": "bags-stands", "id": 21},
            user_context={"cart_items": ["Commute Pack 16"], "saved_items": [], "recent_paid_items": []},
        )
        record_behavior_event(
            user_ref="legacy-user",
            message="Need a phone for daily travel and photos.",
            current_product={"category_slug": "mobile", "id": 99},
            user_context={"cart_items": [], "saved_items": [], "recent_paid_items": []},
        )

        with TemporaryDirectory() as temp_dir:
            model_path = Path(temp_dir) / "model_behavior.json"
            training_path = Path(temp_dir) / "training_data_behavior.json"
            with patch("chatbot.behavior_ai.MODEL_BEHAVIOR_PATH", model_path), patch(
                "chatbot.behavior_ai.TRAINING_DATA_PATH",
                training_path,
            ), patch("chatbot.behavior_ai.fetch_catalog_categories", return_value=RUNTIME_CATEGORIES):
                payload = train_and_save_behavior_model()

            self.assertEqual(payload["version"], 3)
            self.assertEqual(payload["metrics"]["category_count"], 10)
            self.assertIn("audio", payload["priors"])
            self.assertNotIn("laptop", payload["priors"])

            training_payload = json.loads(training_path.read_text(encoding="utf-8"))
            dominant_slugs = {sample["dominant_category_slug"] for sample in training_payload["samples"]}
            self.assertIn("audio", dominant_slugs)
            self.assertIn("bags-stands", dominant_slugs)

    def test_load_knowledge_base_rebuilds_legacy_payload_with_runtime_categories(self):
        legacy_payload = {"version": 1, "documents": [{"doc_type": "product", "doc_id": "legacy"}]}
        product_payload = [
            {
                "id": 11,
                "name": "SkyPhone X",
                "brand": "Apple",
                "price": "1099.00",
                "stock": 28,
                "description": "Flagship phone with strong camera output.",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
            }
        ]

        with TemporaryDirectory() as temp_dir:
            kb_path = Path(temp_dir) / "knowledge_base.json"
            kb_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

            with patch("chatbot.rag_kb.KB_PATH", kb_path), patch(
                "chatbot.rag_kb.fetch_catalog_categories",
                return_value=RUNTIME_CATEGORIES,
            ), patch("chatbot.rag_kb.requests.get", return_value=_json_response(product_payload)):
                payload = load_knowledge_base(auto_build=True)

            self.assertEqual(payload["version"], 3)
            self.assertEqual(payload["stats"]["category_count"], 10)
            product_doc = next(doc for doc in payload["documents"] if doc["doc_type"] == "product")
            self.assertEqual(product_doc["category_slug"], "smartphones")
            self.assertEqual(product_doc["service"], "smartphones")
            self.assertEqual(product_doc["url"], "/customer/products/smartphones/11/")


class ChatbotReplyFlowTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_chat_reply_view_keeps_proxy_compatible_shape_for_dynamic_categories(self):
        recommendations = [
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 11,
                "name": "SkyPhone X",
                "brand": "Apple",
                "description": "Flagship phone with strong camera output.",
                "price": "1099.00",
                "stock": 28,
                "image_url": "",
            }
        ]
        rag_docs = [
            {
                "doc_id": "product:smartphones:11",
                "doc_type": "product",
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "product_id": 11,
                "title": "SkyPhone X",
                "text": "SkyPhone X. Category: Smartphones. Brand: Apple.",
                "url": "/customer/products/smartphones/11/",
                "tokens": ["skyphone", "smartphones", "apple"],
            }
        ]

        with patch("chatbot.behavior_ai.fetch_catalog_categories", return_value=RUNTIME_CATEGORIES), patch(
            "chatbot.services.fetch_catalog_categories",
            return_value=RUNTIME_CATEGORIES,
        ), patch("chatbot.services._fetch_products", return_value=recommendations), patch(
            "chatbot.services.retrieve_rag_context",
            return_value=rag_docs,
        ), patch(
            "chatbot.services._call_llm",
            return_value=("Here are strong phone options for travel and daily use.\n- SkyPhone X", None, "gemma_4_31b"),
        ):
            response = self.client.post(
                "/api/chat/reply/",
                data=json.dumps(
                    {
                        "message": "Can you suggest a good smartphone for travel photos?",
                        "user_ref": "reply-user",
                        "current_product": {
                            "category_slug": "smartphones",
                            "category_name": "Smartphones",
                            "service": "smartphones",
                            "id": 11,
                            "name": "SkyPhone X",
                        },
                        "user_context": {"cart_items": [], "saved_items": [], "recent_paid_items": []},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["fallback_used"])
        self.assertEqual(payload["source"], "gemma_4_31b")
        self.assertEqual(payload["recommendations"][0]["category_slug"], "smartphones")
        self.assertEqual(payload["citations"][0]["url"], "/customer/products/smartphones/11/")
        self.assertIn("SkyPhone X", payload["answer"])

    def test_chat_reply_view_uses_hybrid_model_graph_and_live_context_when_available(self):
        recommendations = [
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 11,
                "name": "SkyPhone X",
                "brand": "Apple",
                "description": "Flagship phone with strong camera output.",
                "price": "1099.00",
                "stock": 28,
                "image_url": "",
            }
        ]
        live_context_products = [
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 11,
                "name": "SkyPhone X",
                "brand": "Apple",
                "description": "Live product_service context for travel and photography.",
                "price": "1099.00",
                "stock": 28,
                "image_url": "",
            }
        ]
        graph_context = {
            "available": True,
            "status": "graph",
            "docs": [
                {
                    "doc_id": "graph:category:smartphones",
                    "doc_type": "graph",
                    "service": "neo4j",
                    "category_slug": "smartphones",
                    "category_name": "Smartphones",
                    "product_id": 0,
                    "title": "Behavior graph for Smartphones",
                    "text": "Graph affinity score: 8.4. Recent behaviors: chatbot_ask, view_product.",
                    "url": "/customer/dashboard/",
                }
            ],
            "product_ids": [11],
            "error": None,
        }
        rag_docs = [
            {
                "doc_id": "faq:shipping",
                "doc_type": "faq",
                "service": "",
                "category_slug": "",
                "category_name": "",
                "product_id": 0,
                "title": "Shipping FAQ",
                "text": "Q: Shipping? A: Standard delivery takes 2-4 days.",
                "url": "/customer/dashboard/#section-faq",
                "tokens": ["shipping", "delivery"],
            }
        ]
        graph_retriever = Mock()
        graph_retriever.fetch_context.return_value = graph_context
        graph_retriever.close.return_value = None

        with patch("chatbot.behavior_ai.fetch_catalog_categories", return_value=RUNTIME_CATEGORIES), patch(
            "chatbot.services.fetch_catalog_categories",
            return_value=RUNTIME_CATEGORIES,
        ), patch(
            "chatbot.services.predict_behavior_for_user_ref",
            return_value={
                "intent_score": 0.71,
                "category_scores": {"smartphones": 0.84},
                "dominant_category_slug": "smartphones",
                "source": "model_best",
                "model_metrics": {"samples": 500},
                "categories": RUNTIME_CATEGORIES,
                "model_best": {
                    "available": True,
                    "selected_category_slug": "smartphones",
                    "reason": "Selected model_best: rnn",
                    "error": None,
                },
            },
        ), patch("chatbot.services._fetch_products", return_value=recommendations), patch(
            "chatbot.services.BehaviorGraphRetriever",
            return_value=graph_retriever,
        ), patch(
            "chatbot.services._fetch_products_by_ids",
            return_value=live_context_products,
        ), patch(
            "chatbot.services.retrieve_rag_context",
            return_value=rag_docs,
        ), patch(
            "chatbot.services._call_llm",
            return_value=("SkyPhone X is a strong fit for travel photos and daily use.\n- SkyPhone X", None, "gemma_4_31b"),
        ):
            response = self.client.post(
                "/api/chat/reply/",
                data=json.dumps(
                    {
                        "message": "Can you suggest a strong phone for travel photos?",
                        "user_ref": "hybrid-user",
                        "current_product": {
                            "category_slug": "smartphones",
                            "category_name": "Smartphones",
                            "service": "smartphones",
                            "id": 11,
                            "name": "SkyPhone X",
                        },
                        "user_context": {"cart_items": [], "saved_items": ["SkyPhone X"], "recent_paid_items": []},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "gemma_4_31b")
        self.assertFalse(payload["fallback_used"])
        self.assertEqual(payload["recommendations"][0]["id"], 11)
        self.assertEqual(payload["citations"][0]["label"], "Behavior graph")
        self.assertEqual(payload["citations"][1]["label"], "Product catalog")
        graph_retriever.fetch_context.assert_called_once()

    def test_chat_reply_view_falls_back_to_heuristic_when_model_best_unavailable(self):
        graph_retriever = Mock()
        graph_retriever.fetch_context.return_value = {"available": False, "status": "empty", "docs": [], "product_ids": [], "error": None}
        graph_retriever.close.return_value = None

        with patch("chatbot.behavior_ai.fetch_catalog_categories", return_value=RUNTIME_CATEGORIES), patch(
            "chatbot.services.fetch_catalog_categories",
            return_value=RUNTIME_CATEGORIES,
        ), patch(
            "chatbot.services.predict_behavior_for_user_ref",
            return_value={
                "intent_score": 0.52,
                "category_scores": {"audio": 0.77},
                "dominant_category_slug": "audio",
                "source": "heuristic",
                "model_metrics": {},
                "categories": RUNTIME_CATEGORIES,
                "model_best": {
                    "available": False,
                    "selected_category_slug": "",
                    "reason": "",
                    "error": "keras_backend_unavailable",
                },
            },
        ), patch(
            "chatbot.services.BehaviorGraphRetriever",
            return_value=graph_retriever,
        ), patch(
            "chatbot.services._fetch_products",
            return_value=[
                {
                    "service": "audio",
                    "category_slug": "audio",
                    "category_name": "Audio",
                    "id": 21,
                    "name": "QuietBeat ANC",
                    "brand": "Sony",
                    "description": "ANC headphones for calls and commuting.",
                    "price": "199.00",
                    "stock": 12,
                    "image_url": "",
                }
            ],
        ), patch(
            "chatbot.services.retrieve_rag_context",
            return_value=[],
        ), patch(
            "chatbot.services._call_llm",
            return_value=("QuietBeat ANC is a good audio pick for commuting.\n- QuietBeat ANC", None, "gemma_4_31b"),
        ):
            response = self.client.post(
                "/api/chat/reply/",
                data=json.dumps(
                    {
                        "message": "Need audio gear for commuting and work calls.",
                        "user_ref": "heuristic-user",
                        "current_product": {
                            "category_slug": "audio",
                            "category_name": "Audio",
                            "service": "audio",
                            "id": 21,
                            "name": "QuietBeat ANC",
                        },
                        "user_context": {"cart_items": [], "saved_items": [], "recent_paid_items": []},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["fallback_used"])
        self.assertEqual(payload["recommendations"][0]["category_slug"], "audio")
        self.assertEqual(graph_retriever.fetch_context.call_args.kwargs["category_slug"], "audio")

    def test_chat_reply_view_keeps_shape_when_model_and_graph_are_unavailable(self):
        graph_retriever = Mock()
        graph_retriever.fetch_context.return_value = {
            "available": False,
            "status": "unavailable",
            "docs": [],
            "product_ids": [],
            "error": "neo4j_query_failed",
        }
        graph_retriever.close.return_value = None
        recommendations = [
            {
                "service": "tablets",
                "category_slug": "tablets",
                "category_name": "Tablets",
                "id": 77,
                "name": "Tab Pro 11",
                "brand": "Samsung",
                "description": "Tablet for study and media.",
                "price": "699.00",
                "stock": 9,
                "image_url": "",
            }
        ]

        with patch("chatbot.behavior_ai.fetch_catalog_categories", return_value=RUNTIME_CATEGORIES), patch(
            "chatbot.services.fetch_catalog_categories",
            return_value=RUNTIME_CATEGORIES,
        ), patch(
            "chatbot.services.predict_behavior_for_user_ref",
            return_value={
                "intent_score": 0.44,
                "category_scores": {"tablets": 0.66},
                "dominant_category_slug": "tablets",
                "source": "heuristic",
                "model_metrics": {},
                "categories": RUNTIME_CATEGORIES,
                "model_best": {
                    "available": False,
                    "selected_category_slug": "",
                    "reason": "",
                    "error": "missing_model_best_artifact",
                },
            },
        ), patch(
            "chatbot.services.BehaviorGraphRetriever",
            return_value=graph_retriever,
        ), patch("chatbot.services._fetch_products", return_value=recommendations), patch(
            "chatbot.services.retrieve_rag_context",
            return_value=[],
        ), patch(
            "chatbot.services._call_llm",
            return_value=(None, "network_error", "gemma_4_31b"),
        ):
            response = self.client.post(
                "/api/chat/reply/",
                data=json.dumps(
                    {
                        "message": "Need a tablet for study notes.",
                        "user_ref": "fallback-user",
                        "current_product": {
                            "category_slug": "tablets",
                            "category_name": "Tablets",
                            "service": "tablets",
                            "id": 77,
                            "name": "Tab Pro 11",
                        },
                        "user_context": {"cart_items": [], "saved_items": [], "recent_paid_items": []},
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["fallback_used"])
        self.assertEqual(payload["source"], "rule_based")
        self.assertEqual(payload["error_code"], "network_error")
        self.assertEqual(payload["recommendations"][0]["category_slug"], "tablets")
        self.assertEqual(payload["citations"], [])
        self.assertIn("catalog recommendations", payload["answer"])

    def test_chat_reply_view_reports_blocked_google_key_without_duplicating_product_list(self):
        graph_retriever = Mock()
        graph_retriever.fetch_context.return_value = {"available": False, "status": "empty", "docs": [], "product_ids": [], "error": None}
        graph_retriever.close.return_value = None
        recommendations = [
            {
                "service": "smartphones",
                "category_slug": "smartphones",
                "category_name": "Smartphones",
                "id": 33,
                "name": "Galaxy Orbit S",
                "brand": "Samsung",
                "description": "Balanced Android flagship.",
                "price": "999.00",
                "stock": 30,
                "image_url": "",
            }
        ]

        with patch("chatbot.behavior_ai.fetch_catalog_categories", return_value=RUNTIME_CATEGORIES), patch(
            "chatbot.services.fetch_catalog_categories",
            return_value=RUNTIME_CATEGORIES,
        ), patch(
            "chatbot.services.BehaviorGraphRetriever",
            return_value=graph_retriever,
        ), patch("chatbot.services._fetch_products", return_value=recommendations), patch(
            "chatbot.services.retrieve_rag_context",
            return_value=[],
        ), patch(
            "chatbot.services._call_llm",
            return_value=(None, "gemini_key_blocked_http_403", "gemini"),
        ):
            response = self.client.post(
                "/api/chat/reply/",
                data=json.dumps({"message": "Goi y dien thoai con hang", "user_ref": "blocked-key-user"}),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["fallback_used"])
        self.assertEqual(payload["error_code"], "gemini_key_blocked_http_403")
        self.assertIn("API key Google AI dang bi chan", payload["answer"])
        self.assertNotIn("Galaxy Orbit S", payload["answer"])
        self.assertEqual(payload["recommendations"][0]["name"], "Galaxy Orbit S")

    def test_call_llm_tries_secondary_provider_before_fallback(self):
        with patch("chatbot.services.get_active_llm_provider", return_value="gemini"), patch(
            "chatbot.services._call_gemini",
            return_value=(None, "gemini_http_429"),
        ), patch(
            "chatbot.services._call_google_gemma",
            return_value=("Gemma answer", None),
        ), patch(
            "chatbot.services._call_openrouter_gemma",
        ) as openrouter_mock:
            answer, error_code, source = services._call_llm("prompt", max_output_tokens=64)

        self.assertEqual(answer, "Gemma answer")
        self.assertIsNone(error_code)
        self.assertEqual(source, "gemma_4_31b")
        openrouter_mock.assert_not_called()


class BehaviorDatasetGenerationTests(TestCase):
    def test_write_behavior_dataset_bundle_matches_phase_one_contract(self):
        valid_slugs = {item["slug"] for item in RUNTIME_CATEGORIES}
        catalog_fixture = _dataset_catalog_fixture()

        with TemporaryDirectory() as temp_dir, patch(
            "chatbot.dataset_generation.fetch_catalog_categories",
            return_value=RUNTIME_CATEGORIES,
        ), patch(
            "chatbot.dataset_generation.load_catalog_products",
            return_value=(catalog_fixture, "test_fixture"),
        ):
            result = write_behavior_dataset_bundle(
                output_dir=Path(temp_dir),
                user_count=500,
                sample_size=20,
                seed=20260420,
            )

            dataset_path = Path(temp_dir) / "data_user500.csv"
            sample_path = Path(temp_dir) / "data_user500_sample20.csv"
            stats_path = Path(temp_dir) / "dataset_stats.json"

            with dataset_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, DATASET_COLUMNS)
                rows = list(reader)

            with sample_path.open("r", encoding="utf-8", newline="") as handle:
                sample_rows = list(csv.DictReader(handle))

            stats = json.loads(stats_path.read_text(encoding="utf-8"))

        self.assertEqual(result["dataset_path"].name, "data_user500.csv")
        self.assertEqual(len(sample_rows), 20)
        self.assertEqual(len({row["user_ref"] for row in rows}), 500)
        self.assertEqual(set(row["behavior_type"] for row in rows), set(OFFICIAL_BEHAVIOR_TYPES))
        self.assertTrue(all(row["category_slug"] in valid_slugs for row in rows))
        self.assertTrue(
            all(
                row["target_next_category_slug"] in valid_slugs or row["target_next_category_slug"] == ""
                for row in rows
            )
        )
        self.assertTrue(
            all(
                bool(row["search_query"]) if row["behavior_type"] in {"search", "chatbot_ask"} else row["search_query"] == ""
                for row in rows
            )
        )

        session_rows = defaultdict(list)
        for row in rows:
            session_rows[(row["user_ref"], row["session_id"])].append(row)

        sessions_per_user = Counter(user_ref for user_ref, _ in session_rows.keys())
        self.assertTrue(all(count >= 4 for count in sessions_per_user.values()))

        for rows_in_session in session_rows.values():
            ordered = sorted(rows_in_session, key=lambda item: (item["event_ts"], int(item["step_index"])))
            self.assertEqual(
                [int(item["step_index"]) for item in ordered],
                list(range(1, len(ordered) + 1)),
            )
            self.assertEqual(ordered[-1]["target_next_category_slug"], "")
            self.assertTrue(all(item["target_next_category_slug"] in valid_slugs for item in ordered[:-1]))

        self.assertEqual(stats["user_count"], 500)
        self.assertEqual(stats["event_count"], len(rows))
        self.assertEqual(stats["session_count"], len(session_rows))
        self.assertEqual(set(stats["behavior_distribution"].keys()), set(OFFICIAL_BEHAVIOR_TYPES))
        self.assertTrue(set(stats["category_distribution"].keys()).issubset(valid_slugs))

    def test_generate_behavior_dataset_command_creates_output_files(self):
        with TemporaryDirectory() as temp_dir, patch(
            "chatbot.dataset_generation.fetch_catalog_categories",
            return_value=RUNTIME_CATEGORIES,
        ), patch(
            "chatbot.dataset_generation.load_catalog_products",
            return_value=(_dataset_catalog_fixture(), "test_fixture"),
        ):
            call_command(
                "generate_behavior_dataset",
                users=60,
                sample_size=20,
                seed=7,
                output_dir=temp_dir,
            )

            self.assertTrue((Path(temp_dir) / "data_user500.csv").exists())
            self.assertTrue((Path(temp_dir) / "data_user500_sample20.csv").exists())
            self.assertTrue((Path(temp_dir) / "dataset_stats.json").exists())


class BehaviorGraphImportTests(TestCase):
    def test_build_behavior_graph_payload_aggregates_preferences_from_dataset(self):
        dataset_rows = [
            {
                "user_ref": "user_0001",
                "event_ts": "2026-01-01T01:00:00Z",
                "step_index": "1",
                "behavior_type": "search",
                "category_slug": "audio",
                "product_id": "0",
                "price_bucket": "unknown",
                "device_type": "mobile",
                "search_query": "wireless audio",
                "session_id": "user_0001_sess_01",
                "target_next_category_slug": "audio",
            },
            {
                "user_ref": "user_0001",
                "event_ts": "2026-01-01T01:03:00Z",
                "step_index": "2",
                "behavior_type": "view_product",
                "category_slug": "audio",
                "product_id": "11",
                "price_bucket": "under_500",
                "device_type": "mobile",
                "search_query": "",
                "session_id": "user_0001_sess_01",
                "target_next_category_slug": "audio",
            },
            {
                "user_ref": "user_0001",
                "event_ts": "2026-01-01T01:06:00Z",
                "step_index": "3",
                "behavior_type": "add_to_cart",
                "category_slug": "audio",
                "product_id": "11",
                "price_bucket": "under_500",
                "device_type": "mobile",
                "search_query": "",
                "session_id": "user_0001_sess_01",
                "target_next_category_slug": "",
            },
            {
                "user_ref": "user_0001",
                "event_ts": "2026-01-08T02:00:00Z",
                "step_index": "1",
                "behavior_type": "search",
                "category_slug": "smartphones",
                "product_id": "0",
                "price_bucket": "unknown",
                "device_type": "mobile",
                "search_query": "camera phone",
                "session_id": "user_0001_sess_02",
                "target_next_category_slug": "smartphones",
            },
            {
                "user_ref": "user_0001",
                "event_ts": "2026-01-08T02:04:00Z",
                "step_index": "2",
                "behavior_type": "view_product",
                "category_slug": "smartphones",
                "product_id": "21",
                "price_bucket": "500_1000",
                "device_type": "mobile",
                "search_query": "",
                "session_id": "user_0001_sess_02",
                "target_next_category_slug": "",
            },
        ]
        catalog_fixture = [
            CatalogProduct(
                product_id=11,
                category_slug="audio",
                category_name="Audio",
                name="QuietBeat ANC",
                brand="Sony",
                price=Decimal("199.00"),
                stock=12,
            ),
            CatalogProduct(
                product_id=21,
                category_slug="smartphones",
                category_name="Smartphones",
                name="SkyPhone X",
                brand="Apple",
                price=Decimal("999.00"),
                stock=8,
            ),
        ]

        with TemporaryDirectory() as temp_dir:
            dataset_path = Path(temp_dir) / "graph_sample.csv"
            with dataset_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=DATASET_COLUMNS)
                writer.writeheader()
                writer.writerows(dataset_rows)

            with patch(
                "chatbot.behavior_graph.fetch_catalog_categories",
                return_value=RUNTIME_CATEGORIES,
            ), patch(
                "chatbot.behavior_graph.load_catalog_products",
                return_value=(catalog_fixture, "test_fixture"),
            ):
                payload = build_behavior_graph_payload(
                    dataset_path=dataset_path,
                    preference_share_threshold=0.18,
                    max_preferences_per_user=3,
                )

        self.assertEqual(payload["stats"]["user_count"], 1)
        self.assertEqual(payload["stats"]["behavior_count"], 5)
        self.assertEqual(payload["stats"]["product_count"], 2)
        self.assertEqual(payload["stats"]["catalog_source"], "test_fixture")
        self.assertEqual(len(payload["preferences"]), 2)
        self.assertEqual(payload["preferences"][0]["category_slug"], "audio")
        self.assertGreater(payload["preferences"][0]["score"], payload["preferences"][1]["score"])
        self.assertEqual(payload["users"][0]["primary_category_slug"], "audio")
        self.assertEqual(payload["behaviors"][1]["product_name"], "QuietBeat ANC")
        self.assertEqual(payload["behaviors"][4]["product_name"], "SkyPhone X")

    def test_import_behavior_graph_command_uses_neo4j_driver_and_reports_stats(self):
        fake_session = Mock()
        fake_session.__enter__ = Mock(return_value=fake_session)
        fake_session.__exit__ = Mock(return_value=False)
        fake_driver = Mock()
        fake_driver.session.return_value = fake_session
        fake_graph_database = Mock()
        fake_graph_database.driver.return_value = fake_driver
        payload = {
            "dataset_path": "C:/tmp/data_user500.csv",
            "categories": [],
            "products": [],
            "users": [],
            "behaviors": [],
            "preferences": [],
            "stats": {
                "user_count": 500,
                "behavior_count": 2200,
                "category_count": 10,
                "product_count": 100,
                "preference_count": 1200,
                "catalog_source": "product_service",
                "missing_product_count": 0,
            },
        }

        stdout = io.StringIO()
        with patch(
            "chatbot.management.commands.import_behavior_graph.build_behavior_graph_payload",
            return_value=payload,
        ), patch(
            "chatbot.management.commands.import_behavior_graph.write_behavior_graph_demo_svg",
            return_value="C:/tmp/behavior_graph_demo.svg",
        ), patch(
            "chatbot.management.commands.import_behavior_graph.sync_behavior_graph",
            return_value=payload["stats"],
        ) as sync_mock, patch(
            "chatbot.management.commands.import_behavior_graph._load_graph_database",
            return_value=fake_graph_database,
        ):
            call_command("import_behavior_graph", reset=True, stdout=stdout)

        fake_graph_database.driver.assert_called_once()
        fake_driver.session.assert_called_once_with(database="neo4j")
        sync_mock.assert_called_once_with(fake_session, payload, clear_existing=True, batch_size=250)
        self.assertIn("behavior graph imported.", stdout.getvalue())
        self.assertIn("demo_graph_path=C:/tmp/behavior_graph_demo.svg", stdout.getvalue())

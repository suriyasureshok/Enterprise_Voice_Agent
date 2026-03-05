voxops-ai-gateway/
│
├── README.md
├── CHECKLIST.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── configs/
│   ├── settings.py
│   └── logging_config.py
│
├── data/
│   ├── demo_orders.csv
│   ├── warehouses.csv
│   ├── routes.csv
│   │
│   └── knowledge_base/
│       ├── company_policies.txt
│       └── faq.txt
│
├── scripts/
│   ├── run_backend.sh
│   ├── seed_database.py
│   └── start_simulation.sh
│
├── tests/
│   ├── test_api.py
│   ├── test_voice.py
│   └── test_simulation.py
│
├── frontend/
│   │
│   ├── voice_client/
│   │   ├── index.html
│   │   ├── app.js
│   │   └── styles.css
│   │
│   └── agent_dashboard/
│       ├── dashboard.html
│       ├── dashboard.js
│       └── dashboard.css
│
└── src/
    │
    └── voxops/
        │
        ├── __init__.py
        │
        ├── backend/
        │   │
        │   ├── main.py
        │   │
        │   ├── api/
        │   │   ├── routes_voice.py
        │   │   ├── routes_orders.py
        │   │   ├── routes_simulation.py
        │   │   └── routes_agent.py
        │   │
        │   └── services/
        │       ├── orchestrator.py
        │       ├── intent_parser.py
        │       ├── response_generator.py
        │       └── agent_handoff.py
        │
        ├── voice/
        │   │
        │   ├── stt/
        │   │   └── whisper_engine.py
        │   │
        │   ├── tts/
        │   │   └── coqui_tts.py
        │   │
        │   └── audio_utils.py
        │
        ├── rag/
        │   ├── document_loader.py
        │   ├── embedding_model.py
        │   ├── vector_store.py
        │   └── retriever.py
        │
        ├── simulation/
        │   ├── route_simulator.py
        │   ├── warehouse_simulator.py
        │   └── delivery_predictor.py
        │
        ├── database/
        │   ├── db.py
        │   ├── models.py
        │   ├── schema.sql
        │   └── seed_data.py
        │
        └── utils/
            ├── logger.py
            └── helpers.py
"""
Causal Knowledge

Facts about cause and effect relationships including:
- Direct cause-effect chains
- Multi-step causal chains
- Prevention and enabling conditions
- Physical causation
- Social causation
"""

CAUSAL_KNOWLEDGE_FACTS = [
    # ── Physical Causation ──
    {"fact_id": "caus_001", "category": "causal", "fact": "Dropping a glass causes it to break", "confidence": 0.9},
    {"fact_id": "caus_002", "category": "causal", "fact": "Heating water causes it to eventually boil", "confidence": 1.0},
    {"fact_id": "caus_003", "category": "causal", "fact": "Cooling water causes it to eventually freeze", "confidence": 1.0},
    {"fact_id": "caus_004", "category": "causal", "fact": "Leaving metal in rain causes it to rust", "confidence": 0.9},
    {"fact_id": "caus_005", "category": "causal", "fact": "Applying force to an object causes it to accelerate", "confidence": 1.0},
    {"fact_id": "caus_006", "category": "causal", "fact": "Releasing an object causes it to fall", "confidence": 1.0},
    {"fact_id": "caus_007", "category": "causal", "fact": "Rubbing hands together causes them to warm up", "confidence": 1.0},
    {"fact_id": "caus_008", "category": "causal", "fact": "Striking a match causes it to ignite", "confidence": 1.0},
    {"fact_id": "caus_009", "category": "causal", "fact": "Turning on a light switch causes the light to turn on", "confidence": 1.0},
    {"fact_id": "caus_010", "category": "causal", "fact": "Plugging in a device causes it to receive power", "confidence": 1.0},
    {"fact_id": "caus_011", "category": "causal", "fact": "Pouring water on fire causes the fire to go out", "confidence": 0.9},
    {"fact_id": "caus_012", "category": "causal", "fact": "Cutting a piece of paper causes it to separate into two pieces", "confidence": 1.0},
    {"fact_id": "caus_013", "category": "causal", "fact": "Squeezing a sponge causes water to come out", "confidence": 1.0},
    {"fact_id": "caus_014", "category": "causal", "fact": "Stretching a rubber band causes it to become longer", "confidence": 1.0},
    {"fact_id": "caus_015", "category": "causal", "fact": "Releasing a stretched rubber band causes it to snap back", "confidence": 1.0},
    {"fact_id": "caus_016", "category": "causal", "fact": "Pressing a button causes an action associated with it", "confidence": 0.9},
    {"fact_id": "caus_017", "category": "causal", "fact": "Opening a door causes access to the other side", "confidence": 1.0},
    {"fact_id": "caus_018", "category": "causal", "fact": "Closing a window causes outside air to stop entering", "confidence": 0.9},
    {"fact_id": "caus_019", "category": "causal", "fact": "Turning a key in a lock causes the lock to open or close", "confidence": 1.0},
    {"fact_id": "caus_020", "category": "causal", "fact": "Adding salt to water causes the water to taste salty", "confidence": 1.0},

    # ── Multi-step Causal Chains ──
    {"fact_id": "caus_101", "category": "causal", "fact": "Not watering plants causes them to wilt and eventually die", "confidence": 1.0},
    {"fact_id": "caus_102", "category": "causal", "fact": "Leaving food out too long causes bacteria to grow and food to spoil", "confidence": 1.0},
    {"fact_id": "caus_103", "category": "causal", "fact": "Not sleeping enough causes tiredness the next day", "confidence": 1.0},
    {"fact_id": "caus_104", "category": "causal", "fact": "Eating too much causes feeling full or sick", "confidence": 0.9},
    {"fact_id": "caus_105", "category": "causal", "fact": "Exercising regularly causes improved fitness over time", "confidence": 1.0},
    {"fact_id": "caus_106", "category": "causal", "fact": "Studying causes better performance on tests", "confidence": 0.9},
    {"fact_id": "caus_107", "category": "causal", "fact": "Saving money causes wealth to accumulate over time", "confidence": 1.0},
    {"fact_id": "caus_108", "category": "causal", "fact": "Not wearing a coat in cold weather causes feeling cold", "confidence": 1.0},
    {"fact_id": "caus_109", "category": "causal", "fact": "Leaving a door open causes heat or cold to escape", "confidence": 0.9},
    {"fact_id": "caus_110", "category": "causal", "fact": "Driving too fast increases the chance of accidents", "confidence": 1.0},
    {"fact_id": "caus_111", "category": "causal", "fact": "Rain causes the ground to become wet", "confidence": 1.0},
    {"fact_id": "caus_112", "category": "causal", "fact": "Sunlight causes plants to grow through photosynthesis", "confidence": 1.0},
    {"fact_id": "caus_113", "category": "causal", "fact": "Smoking causes lung damage over time", "confidence": 1.0},
    {"fact_id": "caus_114", "category": "causal", "fact": "Wearing sunscreen reduces sunburn risk", "confidence": 1.0},
    {"fact_id": "caus_115", "category": "causal", "fact": "Turning off a computer causes it to stop running", "confidence": 1.0},

    # ── Prevention and Enabling Conditions ──
    {"fact_id": "caus_201", "category": "causal", "fact": "Locking a door prevents unauthorized entry", "confidence": 0.9},
    {"fact_id": "caus_202", "category": "causal", "fact": "Wearing a seatbelt reduces injury in car accidents", "confidence": 1.0},
    {"fact_id": "caus_203", "category": "causal", "fact": "Putting food in a fridge prevents it from spoiling quickly", "confidence": 1.0},
    {"fact_id": "caus_204", "category": "causal", "fact": "An umbrella prevents getting wet in the rain", "confidence": 1.0},
    {"fact_id": "caus_205", "category": "causal", "fact": "A password prevents unauthorized access to accounts", "confidence": 0.9},
    {"fact_id": "caus_206", "category": "causal", "fact": "A backup prevents data loss if hardware fails", "confidence": 1.0},
    {"fact_id": "caus_207", "category": "causal", "fact": "Washing hands prevents the spread of germs", "confidence": 1.0},
    {"fact_id": "caus_208", "category": "causal", "fact": "Having a key enables opening a locked door", "confidence": 1.0},
    {"fact_id": "caus_209", "category": "causal", "fact": "Having fuel enables a car to run", "confidence": 1.0},
    {"fact_id": "caus_210", "category": "causal", "fact": "Having electricity enables electronic devices to work", "confidence": 1.0},
    {"fact_id": "caus_211", "category": "causal", "fact": "Having internet enables browsing the web", "confidence": 1.0},
    {"fact_id": "caus_212", "category": "causal", "fact": "A sharp knife enables clean cutting", "confidence": 1.0},
    {"fact_id": "caus_213", "category": "causal", "fact": "Insulation prevents heat loss from buildings", "confidence": 1.0},
    {"fact_id": "caus_214", "category": "causal", "fact": "Fire extinguishers prevent small fires from becoming large", "confidence": 1.0},
    {"fact_id": "caus_215", "category": "causal", "fact": "Vaccines prevent certain diseases", "confidence": 1.0},

    # ── Social Causation ──
    {"fact_id": "caus_301", "category": "causal", "fact": "Being kind to people causes them to like you more", "confidence": 0.8},
    {"fact_id": "caus_302", "category": "causal", "fact": "Lying causes loss of trust when discovered", "confidence": 1.0},
    {"fact_id": "caus_303", "category": "causal", "fact": "Breaking promises damages relationships", "confidence": 1.0},
    {"fact_id": "caus_304", "category": "causal", "fact": "Helping someone causes them to feel grateful", "confidence": 0.9},
    {"fact_id": "caus_305", "category": "causal", "fact": "Insulting someone causes them to feel hurt or angry", "confidence": 1.0},
    {"fact_id": "caus_306", "category": "causal", "fact": "Apologizing after a mistake can repair relationships", "confidence": 0.9},
    {"fact_id": "caus_307", "category": "causal", "fact": "Working hard causes better job performance", "confidence": 0.9},
    {"fact_id": "caus_308", "category": "causal", "fact": "Missing deadlines causes loss of professional trust", "confidence": 1.0},
    {"fact_id": "caus_309", "category": "causal", "fact": "Sharing causes others to be more willing to share with you", "confidence": 0.8},
    {"fact_id": "caus_310", "category": "causal", "fact": "Listening to someone makes them feel heard and valued", "confidence": 0.9},
]

import pyoxigraph as ox
import pytest

from managraph import rules

# A cut-down CR with the same layout as the real one: table of contents,
# Credits, the numbered rules, then the glossary.
CR = """﻿Magic: The Gathering Comprehensive Rules

These rules are effective as of November 6, 2026.

Contents

1. Game Concepts
205. Type Line
Glossary
Credits

1. Game Concepts

205.2a The card types are artifact, creature, instant, kindred, land, plane, and sorcery. See section 3, "Card Types."

205.3g Artifacts have their own unique set of subtypes; these subtypes are called artifact types. The artifact types are Equipment (see rule 301.5), Spacecraft, and Treasure.

205.3h Enchantments have their own unique set of subtypes; these subtypes are called enchantment types. The enchantment types are Aura (see rule 303.4) and Saga.

205.3i Lands have their own unique set of subtypes; these subtypes are called land types. The land types are Forest, Gate, Island, and Urza’s. Of that list, Forest and Island are the basic land types. See rule 305.6.

205.3j Planeswalkers have their own unique set of subtypes; these subtypes are called planeswalker types. The planeswalker types are Ajani and Chandra.

205.3k Instants and sorceries share their lists of subtypes; these subtypes are called spell types. The spell types are Adventure and Arcane.

205.3m Creatures and kindreds share their lists of subtypes; these subtypes are called creature types. One creature type is two words long: Time Lord. All other creature types are one word long: Elf, Goblin, and Shapeshifter.

205.3n Planes have their own unique set of subtypes; these subtypes are called planar types. The planar types are The Abyss, Bolas’s Meditation Realm, and Spacecraft.

205.3p One dungeon card (Undercity) has a subtype; this subtype is called a dungeon type. That dungeon type is Undercity.

205.3q Battles have a unique subtype, called a battle type. That battle type is Siege.

205.4a An object can have one or more supertypes. A card’s supertypes are printed directly before its card types. The supertypes are basic, legendary, and snow.

207.2c An ability word appears in italics at the beginning of some abilities. The ability words are landfall and will of the council.

301. Artifacts
302. Creatures
304. Instants
305. Lands
307. Sorceries
308. Kindreds
311. Planes

701.1. Most actions described in a card’s rules text use the standard English definitions.
701.2. Scry
701.3. Venture into the Dungeon

702.1. Most abilities describe exactly what they do in the card’s rules text.
702.2. Flying
702.3. For Mirrodin!
702.4. Changeling

Glossary

Flying
A keyword ability.

Credits
"""


@pytest.fixture(scope="module")
def parsed():
    return rules.parse(CR.replace("﻿", ""))


def test_effective_date(parsed):
    assert parsed.effective == "2026-11-06"


def test_card_types_with_sections(parsed):
    assert parsed.card_types == {
        "Artifact": "301", "Creature": "302", "Instant": "304", "Kindred": "308",
        "Land": "305", "Plane": "311", "Sorcery": "307",
    }


def test_supertypes(parsed):
    assert parsed.supertypes == ["Basic", "Legendary", "Snow"]


def test_subtypes(parsed):
    assert parsed.subtypes["artifact"] == ["Equipment", "Spacecraft", "Treasure"]
    assert parsed.subtypes["enchantment"] == ["Aura", "Saga"]
    assert parsed.subtypes["creature"] == ["Elf", "Goblin", "Shapeshifter", "Time Lord"]
    assert parsed.subtypes["planar"] == ["Bolas’s Meditation Realm", "Spacecraft", "The Abyss"]
    assert parsed.subtypes["dungeon"] == ["Undercity"]
    assert parsed.subtypes["battle"] == ["Siege"]
    assert parsed.basic_land_types == ["Forest", "Island"]


def test_keywords(parsed):
    assert parsed.keyword_actions == {"Scry": "701.2", "Venture into the Dungeon": "701.3"}
    assert parsed.keyword_abilities == {"Flying": "702.2", "For Mirrodin!": "702.3", "Changeling": "702.4"}
    assert parsed.ability_words == ["landfall", "will of the council"]


def test_find_rules_url():
    html = '<a href="https://media.wizards.com/2026/downloads/MagicCompRules 20261106.txt">TXT</a>'
    assert rules.find_rules_url(html) == "https://media.wizards.com/2026/downloads/MagicCompRules%2020261106.txt"


def _load(*ttl):
    store = ox.Store()
    for text in ttl:
        store.load(text.encode("utf-8"), format=ox.RdfFormat.TURTLE)
    return store


def test_types_ttl(parsed):
    store = _load(rules.types_ttl(parsed))
    ask = lambda q: store.query("PREFIX mg: <https://w3id.org/managraph/ontology#> ASK { " + q + " }")
    base = "https://w3id.org/managraph/type/"
    assert ask(f"<{base}artifact/Spacecraft> a mg:ArtifactType")
    assert ask(f"<{base}planar/Spacecraft> a mg:PlanarType")
    assert ask(f"<{base}land/Forest> a mg:BasicLandType")
    assert ask(f"<{base}land/Urzas> a mg:LandType")
    assert ask(f"<{base}creature/Time_Lord> a mg:CreatureType")
    assert ask(f'<{base}card/Kindred> <http://www.w3.org/2004/02/skos/core#altLabel> "Tribal"@en')
    # Changeling grants every creature type
    granted = store.query("""
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT (COUNT(?type) AS ?n) WHERE {
            ?cond owl:intersectionOf ?list ; rdfs:subClassOf [ owl:hasValue ?type ] .
        }""")
    assert int(next(granted)["n"].value) == len(parsed.subtypes["creature"])


def test_keywords_ttl(parsed):
    store = _load(rules.keywords_ttl(parsed))
    ask = lambda q: store.query("PREFIX mg: <https://w3id.org/managraph/ontology#> ASK { " + q + " }")
    base = "https://w3id.org/managraph/keyword/"
    assert ask(f'<{base}changeling> a mg:KeywordAbility ; mg:ruleSection "702.4"')
    assert ask(f"<{base}for_mirrodin> a mg:KeywordAbility")
    assert ask(f"<{base}venture_into_the_dungeon> a mg:KeywordAction")
    assert ask(f'<{base}will_of_the_council> a mg:AbilityWord ; <http://www.w3.org/2000/01/rdf-schema#label> "Will of the council"@en')

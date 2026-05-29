#!/usr/bin/env python
"""Seed the mock MCP SQLite database with I14Y-style concepts."""

import asyncio
import json
from pathlib import Path

import aiosqlite

DB_PATH = Path("data/mock.db")

CONCEPTS = [
    # Person concepts
    ("person.full_name", "Person.FullName", "Full name of a person (given + family)", "STRING",
     "https://ld.admin.ch/property/fullName", "Person", ["name", "full_name", "display_name", "nom", "name_full"]),
    ("person.given_name", "Person.GivenName", "First/given name of a person", "STRING",
     "https://ld.admin.ch/property/givenName", "Person", ["first_name", "vorname", "prenom", "given_name"]),
    ("person.family_name", "Person.FamilyName", "Family/last name of a person", "STRING",
     "https://ld.admin.ch/property/familyName", "Person", ["last_name", "nachname", "nom_de_famille", "surname"]),
    ("person.date_of_birth", "Person.DateOfBirth", "Date of birth of a person (ISO 8601)", "DATE",
     "https://ld.admin.ch/property/dateOfBirth", "Person", ["birth_date", "dob", "date_naissance", "geburtsdatum", "birthday"]),
    ("person.ahv_number", "Person.AHV_Number", "Swiss social security number (AHV/AVS/AVS)", "STRING",
     "https://ld.admin.ch/property/ahvNumber", "Person", ["ahv", "avs", "ssn", "social_security"]),
    ("person.gender", "Person.Gender", "Gender of a person", "STRING",
     "https://ld.admin.ch/property/gender", "Person", ["sex", "geschlecht", "sexe", "gender"]),
    ("person.nationality", "Person.Nationality", "Nationality of a person (ISO 3166-1 alpha-2)", "STRING",
     "https://ld.admin.ch/property/nationality", "Person", ["country", "citizenship", "nationalite", "staatsangehoerigkeit"]),

    # Address concepts
    ("address.municipality", "Address.Municipality", "Name of Swiss municipality (Gemeinde)", "STRING",
     "https://ld.admin.ch/property/municipalityName", "Address", ["gemeinde", "gemeinde_name", "commune", "city", "municipality", "ort"]),
    ("address.postal_code", "Address.PostalCode", "Swiss postal code (PLZ/NPA)", "INTEGER",
     "https://ld.admin.ch/property/postalCode", "Address", ["plz", "zip", "npa", "postleitzahl", "code_postal", "postal_code", "zipcode"]),
    ("address.street", "Address.Street", "Street name and number", "STRING",
     "https://ld.admin.ch/property/street", "Address", ["strasse", "rue", "via", "street_address", "adresse"]),
    ("address.canton", "Address.CantonCode", "Swiss canton abbreviation (e.g. ZH, BE)", "STRING",
     "https://ld.admin.ch/property/cantonAbbreviation", "Address", ["kanton", "canton", "kanton_kuerzel", "canton_code"]),
    ("address.country", "Address.Country", "Country code (ISO 3166-1 alpha-2)", "STRING",
     "https://ld.admin.ch/property/countryCode", "Address", ["land", "pays", "country_code", "nation"]),

    # BFS-specific
    ("bfs.municipality_number", "BFS.MunicipalityNumber", "Official BFS municipality number (Gemeindenummer)", "INTEGER",
     "https://ld.admin.ch/property/bfsNumber", "BFS", ["bfs_nr", "bfs_nummer", "no_commune", "gemeindenummer", "municipality_id", "gemeinde_id"]),
    ("bfs.canton_number", "BFS.CantonNumber", "Official BFS canton number", "INTEGER",
     "https://ld.admin.ch/property/cantonNumber", "BFS", ["kanton_nr", "canton_nr", "canton_number"]),

    # Organisation concepts
    ("org.uid", "Organisation.UID", "Swiss enterprise identification number (UID)", "STRING",
     "https://ld.admin.ch/property/uid", "Organisation", ["uid", "uid_number", "enterprise_id", "firmen_id"]),
    ("org.name", "Organisation.Name", "Legal name of the organisation", "STRING",
     "https://ld.admin.ch/property/legalName", "Organisation", ["company_name", "firm_name", "firmenname", "raison_sociale", "organisation"]),
    ("org.legal_form", "Organisation.LegalForm", "Legal form of the organisation (AG, GmbH, etc.)", "STRING",
     "https://ld.admin.ch/property/legalForm", "Organisation", ["rechtsform", "forme_juridique", "legal_form"]),

    # Generic identifiers
    ("id.local_id", "Identifier.LocalID", "Local system identifier for an entity", "STRING",
     "https://ld.admin.ch/property/localIdentifier", "Identifier", ["id", "local_id", "record_id", "emp_id", "contact_id", "user_id"]),
    ("id.external_ref", "Identifier.ExternalReference", "External reference identifier", "STRING",
     "https://ld.admin.ch/property/externalReference", "Identifier", ["ref", "external_id", "reference_id"]),

    # Economic data
    ("econ.amount_chf", "Economy.AmountCHF", "Monetary amount in Swiss Francs", "FLOAT",
     "https://ld.admin.ch/property/amountCHF", "Economy", ["salary_chf", "revenue_chf", "amount_chf", "betrag_chf", "montant_chf", "value_chf"]),
    ("econ.year", "Time.ReferenceYear", "Reference year for statistical data", "INTEGER",
     "https://ld.admin.ch/property/referenceYear", "Time", ["year", "jahr", "annee", "reference_year", "reporting_year"]),
    ("econ.population", "Statistics.Population", "Population count", "INTEGER",
     "https://ld.admin.ch/property/populationCount", "Statistics", ["einwohner", "population", "bevoelkerung", "total_bevoelkerung", "habitants"]),

    # Contact
    ("contact.email", "Contact.Email", "Email address", "STRING",
     "https://ld.admin.ch/property/email", "Contact", ["email", "email_address", "e_mail", "courriel"]),
    ("contact.phone", "Contact.Phone", "Phone number", "STRING",
     "https://ld.admin.ch/property/phoneNumber", "Contact", ["phone", "telefon", "telephone", "tel", "mobile"]),

    # Employment
    ("employment.department", "Employment.Department", "Organisational department or unit", "STRING",
     "https://ld.admin.ch/property/department", "Employment", ["department", "abteilung", "departement", "unit", "division"]),
    ("employment.hire_date", "Employment.HireDate", "Date when employee was hired", "DATE",
     "https://ld.admin.ch/property/hireDate", "Employment", ["hire_date", "start_date", "eintrittsdatum", "date_entree"]),
]


async def seed() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS concepts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                data_type TEXT DEFAULT 'STRING',
                uri TEXT,
                category TEXT,
                aliases TEXT
            )
            """
        )
        await db.execute("DELETE FROM concepts")

        for concept in CONCEPTS:
            cid, name, desc, dtype, uri, category, aliases = concept
            await db.execute(
                "INSERT INTO concepts (id, name, description, data_type, uri, category, aliases) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cid, name, desc, dtype, uri, category, json.dumps(aliases)),
            )

        await db.commit()
        print(f"[OK] Seeded {len(CONCEPTS)} I14Y concepts into {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(seed())

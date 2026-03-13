#!/usr/bin/env python3
"""
PostGIS generalisering med ST_SimplifyPreserveTopology.

Denna metod är optimal för att behålla topologisk korrekthet.
"""

import psycopg2
from psycopg2 import sql
import subprocess
import logging
from pathlib import Path
import geopandas as gpd

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

# PostgreSQL-anslutningsparametrar
DB_NAME = "nmd_generalize"
DB_USER = "hcn"
DB_PASSWORD = "nmd123"
TABLE_NAME = "polygons"
DIST_TOLERANCE = 20  # meter - generaliserings-tolerance

def create_database():
    """Skapa PostgreSQL-databas med PostGIS."""
    log.info("🔧 Skapar PostgreSQL-databas...")
    
    try:
        # Anslut till postgres-databasen
        conn = psycopg2.connect(
            database="postgres",
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Kolla om databasen redan finns
        cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
        if not cur.fetchone():
            log.info(f"   • Skapar databas '{DB_NAME}'...")
            cur.execute(sql.SQL("CREATE DATABASE {}").format(
                sql.Identifier(DB_NAME)
            ))
        else:
            log.info(f"   • Databasen '{DB_NAME}' finns redan")
        
        cur.close()
        conn.close()
        
        # Anslut till den nya databasen och aktivera PostGIS
        conn = psycopg2.connect(
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        try:
            log.info(f"   • Aktiverar PostGIS...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            log.info(f"   ✓ PostGIS är aktiverat")
        except psycopg2.Error as e:
            log.error(f"   ✗ Kunde inte aktivera PostGIS: {e}")
        
        cur.close()
        conn.close()
        return True
        
    except psycopg2.Error as e:
        log.error(f"✗ Databasfel: {e}")
        return False

def import_gpkg_to_postgres(gpkg_file):
    """Importera GPKG-fil till PostGIS med ogr2ogr."""
    log.info(f"📥 Importerar GPKG till PostGIS...")
    
    gpkg_file = Path(gpkg_file)
    if not gpkg_file.exists():
        log.error(f"   ✗ Fil finns inte: {gpkg_file}")
        return False
    
    # Använd ogr2ogr för import
    cmd = [
        "ogr2ogr",
        "-f", "PostgreSQL",
        f"PG:dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}",
        str(gpkg_file),
        "-nln", TABLE_NAME,
        "-overwrite"
    ]
    
    try:
        log.info(f"   • Kör ogr2ogr...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            log.info(f"   ✓ GPKG importerad")
            return True
        else:
            log.error(f"   ✗ ogr2ogr fel: {result.stderr}")
            return False
    except Exception as e:
        log.error(f"   ✗ Import misslyckades: {e}")
        return False

def generalize_with_postgis(tolerance=DIST_TOLERANCE):
    """Använd PostGIS ST_SimplifyPreserveTopology för generalisering."""
    log.info(f"\n🔄 Generaliserar med PostGIS...")
    log.info(f"   • Tolerance: {tolerance} meter")
    
    try:
        conn = psycopg2.connect(
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        
        # Hitta geometry-kolumnen
        log.info(f"   • Hittar geometry-kolumn...")
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = %s AND udt_name = 'geometry'
        """, (TABLE_NAME,))
        
        result = cur.fetchone()
        if not result:
            log.error(f"   ✗ Ingen geometry-kolumn hittad")
            return False
        
        geom_column = result[0]
        log.info(f"   ✓ Geometri-kolumn: '{geom_column}'")
        
        # Kolla ursprungligt antal
        log.info(f"   • Räknar ursprungliga polygoner...")
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        orig_count = cur.fetchone()[0]
        log.info(f"     Före: {orig_count:,} polygoner")
        
        # Skapa ny tabell med höjd geometri
        log.info(f"   • Tillämpar ST_SimplifyPreserveTopology...")
        cur.execute(f"""
            ALTER TABLE {TABLE_NAME}
            ADD COLUMN geom_simplified geometry
        """)
        
        cur.execute(f"""
            UPDATE {TABLE_NAME}
            SET geom_simplified = ST_SimplifyPreserveTopology({geom_column}, {tolerance})
        """)
        
        log.info(f"   • Byter till förenkl geometri...")
        cur.execute(f"""
            ALTER TABLE {TABLE_NAME}
            DROP COLUMN {geom_column};
            ALTER TABLE {TABLE_NAME}
            RENAME COLUMN geom_simplified TO {geom_column};
        """)
        
        # Räkna resultatet
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        result_count = cur.fetchone()[0]
        log.info(f"     Efter: {result_count:,} polygoner")
        
        cur.close()
        conn.commit()
        conn.close()
        
        log.info(f"   ✓ Generalisering klar!")
        return True
        
    except psycopg2.Error as e:
        log.error(f"   ✗ PostGIS-fel: {e}")
        return False

def export_from_postgis(output_gpkg):
    """Exportera generaliserad data från PostGIS tillbaka till GPKG."""
    log.info(f"\n📤 Exporterar till GPKG...")
    
    output_gpkg = Path(output_gpkg)
    
    # Använd ogr2ogr för export
    cmd = [
        "ogr2ogr",
        "-f", "GPKG",
        str(output_gpkg),
        f"PG:dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}",
        "-sql", f"SELECT * FROM {TABLE_NAME}"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0 and output_gpkg.exists():
            size = output_gpkg.stat().st_size / 1e6
            log.info(f"   ✓ {output_gpkg.name}")
            log.info(f"   ✓ {size:.2f} MB")
            return True
        else:
            log.error(f"   ✗ ogr2ogr export-fel: {result.stderr}")
            return False
    except Exception as e:
        log.error(f"   ✗ Export misslyckades: {e}")
        return False

def main():
    log.info("═" * 60)
    log.info("PostGIS topologisk generalisering")
    log.info("═" * 60)
    
    SOURCE_GPKG = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/generalized_modal_k15.gpkg")
    OUTPUT_GPKG = SOURCE_GPKG.parent / (SOURCE_GPKG.stem + "_postgis.gpkg")
    
    # 1. Skapa databas
    if not create_database():
        return False
    
    # 2. Importera GPKG
    if not import_gpkg_to_postgres(SOURCE_GPKG):
        return False
    
    # 3. Generalisera
    if not generalize_with_postgis(tolerance=DIST_TOLERANCE):
        return False
    
    # 4. Exportera
    if not export_from_postgis(OUTPUT_GPKG):
        return False
    
    log.info("\n✅ PostGIS-generalisering klar!")
    log.info(f"   Resultat: {OUTPUT_GPKG}")
    
    return True

if __name__ == "__main__":
    main()

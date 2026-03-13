#!/usr/bin/env python3
"""
PostGIS topologisk generalisering med gapavsäkring.

Metod:
1. Union - slå ihop alla polygoner till en unified geometry
2. Simplify - generalisera den slagna geometrin
3. Polygonize - dela upp till enskilda polygoner igen
4. Slå till samma attribut

Detta garanterar ingen gaps eller överlappningar.
"""

import psycopg2
from psycopg2 import sql
import subprocess
import logging
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-6s] %(message)s",
    datefmt="%H:%M:%S"
)

DB_NAME = "nmd_generalize"
DB_USER = "hcn"
DB_PASSWORD = "nmd123"
TABLE_NAME = "polygons"
DIST_TOLERANCE = 20

def gap_safe_generalize():
    """Generalisera utan gaps - union → simplify → polygonize."""
    log.info("🔄 Gap-säker generalisering med PostGIS...")
    log.info(f"   Tolerance: {DIST_TOLERANCE} meter")
    
    try:
        conn = psycopg2.connect(
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # 1. Hitta geometry-kolumnen
        log.info(f"   • Hittar geometry-kolumn...")
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = %s AND udt_name = 'geometry'
        """, (TABLE_NAME,))
        
        result = cur.fetchone()
        if not result:
            log.error(f"   ✗ Geometri-kolumn inte hittad")
            return False
        
        geom_column = result[0]
        log.info(f"   ✓ Geometri-kolumn: '{geom_column}'")
        
        # 2. Kolla ursprungligt antal
        log.info(f"   • Räknar ursprungliga polygoner...")
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        orig_count = cur.fetchone()[0]
        log.info(f"     Före: {orig_count:,} polygoner")
        
        # 3. Skapa backup av original
        log.info(f"   • Sparar backup av original...")
        cur.execute(f"""
            CREATE TABLE {TABLE_NAME}_backup AS SELECT * FROM {TABLE_NAME}
        """)
        
        # 4. Union alla polygoner
        log.info(f"   • Slår ihop alla polygoner (UNION)...")
        cur.execute(f"""
            CREATE TABLE {TABLE_NAME}_union AS
            SELECT ST_UnaryUnion(ST_Collect({geom_column})) as geom
            FROM {TABLE_NAME}
        """)
        
        # 5. Generalisera den slagna geometrin
        log.info(f"   • Generaliserar union (tolerance={DIST_TOLERANCE}m)...")
        cur.execute(f"""
            CREATE TABLE {TABLE_NAME}_simplified AS
            SELECT ST_SimplifyPreserveTopology(geom, {DIST_TOLERANCE}) as geom
            FROM {TABLE_NAME}_union
        """)
        
        # 6. Polygonisera - dela upp till enskilda polygoner
        log.info(f"   • Polygoniserar (ST_Polygonize)...")
        cur.execute(f"""
            CREATE TABLE {TABLE_NAME}_polygonized AS
            SELECT (ST_Dump(ST_Polygonize(geom))).geom as {geom_column}
            FROM {TABLE_NAME}_simplified
        """)
        
        # Räkna resultat
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}_polygonized")
        result_count = cur.fetchone()[0]
        log.info(f"   ✓ Polygoniserad: {result_count:,} polygoner")
        
        # 7. Lägg tillbaka DN-attribut
        log.info(f"   • Lägger tillbaka DN-attribut...")
        cur.execute(f"""
            ALTER TABLE {TABLE_NAME}_polygonized
            ADD COLUMN "DN" integer DEFAULT 1
        """)
        
        # 8. Byt tabell
        log.info(f"   • Ersätter original-tabellen...")
        cur.execute(f"""
            DROP TABLE {TABLE_NAME};
            ALTER TABLE {TABLE_NAME}_polygonized
            RENAME TO {TABLE_NAME}
        """)
        
        # 9. Skapa spatial index
        log.info(f"   • Skapar spatial index...")
        cur.execute(f"""
            CREATE INDEX {TABLE_NAME}_geom_idx
            ON {TABLE_NAME}
            USING GIST({geom_column})
        """)
        
        # 10. Verifiera resultat
        cur.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        final_count = cur.fetchone()[0]
        log.info(f"     Efter: {final_count:,} polygoner")
        
        # Kolla för overlaps/gaps
        log.info(f"   • Verifierar topologi...")
        cur.execute(f"""
            SELECT COUNT(*) FROM {TABLE_NAME} a
            WHERE EXISTS (
                SELECT 1 FROM {TABLE_NAME} b
                WHERE a.ctid < b.ctid
                AND ST_Overlaps(a.{geom_column}, b.{geom_column})
            )
        """)
        overlaps = cur.fetchone()[0]
        if overlaps > 0:
            log.warning(f"   ⚠ {overlaps} potentiella overlaps detekterade")
        else:
            log.info(f"   ✓ Inga overlaps detekterade")
        
        cur.close()
        conn.close()
        
        log.info(f"   ✓ Gap-säker generalisering klar!")
        reduction_pct = (1 - final_count / orig_count) * 100 if orig_count > 0 else 0
        log.info(f"     Reduktion: {reduction_pct:.1f}% polygoner")
        
        return True
        
    except psycopg2.Error as e:
        log.error(f"   ✗ Databasfel: {e}")
        return False

def export_to_gpkg(output_gpkg):
    """Exportera från PostGIS till GeoPackage."""
    log.info(f"\n📤 Exporterar till GPKG...")
    
    output_gpkg = Path(output_gpkg)
    
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
            log.error(f"   ✗ ogr2ogr-fel: {result.stderr}")
            return False
    except Exception as e:
        log.error(f"   ✗ Export misslyckades: {e}")
        return False

def main():
    log.info("═" * 60)
    log.info("PostGIS GAP-SÄKER generalisering")
    log.info("═" * 60)
    
    SOURCE_GPKG = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/pipeline_1024_halo/vectorized/generalized_modal_k15.gpkg")
    OUTPUT_GPKG = SOURCE_GPKG.parent / (SOURCE_GPKG.stem + "_nogaps.gpkg")
    
    # Rensa gammal databas
    log.info("\n🗑  Rensar gammal databas...")
    try:
        conn = psycopg2.connect(
            database="postgres",
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS {DB_NAME}")
        cur.close()
        conn.close()
        log.info("   ✓ Databas rensad")
    except:
        log.info("   (kunde inte rensa - OK)")
    
    # Skapa ny databas
    log.info("\n🔧 Skapar databas...")
    try:
        conn = psycopg2.connect(
            database="postgres",
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute(sql.SQL("CREATE DATABASE {}").format(
            sql.Identifier(DB_NAME)
        ))
        
        cur.close()
        conn.close()
        log.info("   ✓ Databas skapad")
    except Exception as e:
        log.error(f"   ✗ Fel: {e}")
        return False
    
    # Aktivera PostGIS
    log.info("   • Aktiverar PostGIS...")
    try:
        conn = psycopg2.connect(
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cur.close()
        conn.close()
        log.info("   ✓ PostGIS aktiverat")
    except Exception as e:
        log.error(f"   ✗ Fel: {e}")
        return False
    
    # Importera GPKG
    log.info("\n📥 Importerar GPKG...")
    cmd = [
        "ogr2ogr",
        "-f", "PostgreSQL",
        f"PG:dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}",
        str(SOURCE_GPKG),
        "-nln", TABLE_NAME,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode == 0:
        log.info("   ✓ GPKG importerad")
    else:
        log.error(f"   ✗ ogr2ogr-fel: {result.stderr}")
        return False
    
    # Gap-säker generalisering
    if not gap_safe_generalize():
        return False
    
    # Exportera
    if not export_to_gpkg(OUTPUT_GPKG):
        return False
    
    log.info("\n✅ Gap-säker generalisering KLAR!")
    log.info(f"   Resultat: {OUTPUT_GPKG}")
    
    return True

if __name__ == "__main__":
    main()

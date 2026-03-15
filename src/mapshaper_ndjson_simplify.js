#!/usr/bin/env node
/**
 * mapshaper_ndjson_simplify.js
 *
 * Läser ndjson (radbruten GeoJSON, en feature per rad), utför topologibevarande
 * förenkling via Mapshapers Node.js-API och skriver GeoJSON-utdata till fil.
 *
 * Fördelen jämfört med mapshaper CLI:
 *   – input skickas som ett JS-objekt (FeatureCollection) → ingen TextDecoder.decode()
 *     → ingen V8-stränggräns (~512 MB) för input
 *   – utdata returneras som en Buffer → ingen V8-stränggräns för output heller
 *
 * Anrop: node mapshaper_ndjson_simplify.js <input.geojsonl> <output.geojson> <tolerance_pct>
 *   tolerance_pct — heltal 1–100, andel kvarvarande borttagbara hörn (15 = 15%)
 */

'use strict';

const readline = require('readline');
const fs = require('fs');
const path = require('path');

const [, , inputFile, outputFile, tolerancePct] = process.argv;

if (!inputFile || !outputFile || !tolerancePct) {
  console.error('Användning: node mapshaper_ndjson_simplify.js <input.geojsonl> <output.geojson> <tolerance_pct>');
  process.exit(1);
}

// require('mapshaper') löses via NODE_PATH satt av anroparen (steg_8_simplify.py)
const mapshaper = require('mapshaper');

const features = [];
const rl = readline.createInterface({
  input: fs.createReadStream(inputFile),
  crlfDelay: Infinity,
});

rl.on('line', (line) => {
  const trimmed = line.trim();
  if (trimmed) {
    features.push(JSON.parse(trimmed));
  }
});

rl.on('close', () => {
  process.stderr.write(`[mapshaper_ndjson] Läste ${features.length} features\n`);

  const geojson = { type: 'FeatureCollection', features };

  const cmd = [
    '-i layer.geojson',
    `-simplify percentage=${tolerancePct}% planar keep-shapes`,
    '-o layer_out.geojson format=geojson',
  ].join(' ');

  mapshaper.applyCommands(
    cmd,
    { 'layer.geojson': geojson },
    (err, output) => {
      if (err) {
        process.stderr.write(`[mapshaper_ndjson] FEL: ${err.message}\n`);
        process.exit(1);
      }
      const buf = output['layer_out.geojson'];
      fs.writeFileSync(outputFile, buf);
      process.stderr.write(`[mapshaper_ndjson] Skrev ${Math.round(buf.length / 1e6)} MB → ${outputFile}\n`);
    }
  );
});

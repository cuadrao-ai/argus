import test from 'node:test';
import assert from 'node:assert/strict';
import { segments, nearestIndex, formattedDate, formattedValue } from './model.mjs';
import { readFile } from 'node:fs/promises';
const fixture=JSON.parse(await readFile(new URL('../fixtures/series.json',import.meta.url)));
test('each supplied fact appears once in a segment and no segment crosses a null',()=>{
  for(const scenario of fixture.cases) for(const key of ['actual','projected']) {
    const output=segments(scenario.points,key);
    assert.deepEqual(output.flat(),scenario.points.filter(p=>p[key]!==null).map(p=>({time:p.time,value:p[key]})));
    for(const segment of output) {
      const first=scenario.points.findIndex(p=>p.time===segment[0].time);
      assert.ok(scenario.points.slice(first,first+segment.length).every(p=>p[key]!==null));
    }
  }
});
test('selection clamps endpoints, includes gaps, and resolves ties earlier',()=>{
  assert.equal(nearestIndex(-100,10),0);
  assert.equal(nearestIndex(100,10),9);
  assert.equal(nearestIndex(4.5,10),4);
  assert.equal(nearestIndex(4.51,10),5);
  assert.equal(nearestIndex(1,0),null);
  assert.equal(nearestIndex(null,10),null);
});
test('formatting preserves zero, negative, missing, currency and UTC civil dates',()=>{
  for(const locale of ['en','es-419']) {
    assert.match(formattedValue(0,'DOP',locale),/DOP.*0[.,]00/);
    assert.match(formattedValue(-10,'USD',locale),/-/);
    assert.match(formattedDate('2026-01-01',locale),/2026/);
  }
  assert.equal(formattedValue(null,'USD','en'),'No data');
  assert.equal(formattedValue(null,'USD','es-419'),'Sin datos');
});

import assert from 'node:assert/strict';
import test from 'node:test';
import {distanceKm, placeLink, pointPayload, rankedPlaces, regionPayload, safeURL, validPoint} from '../../../apps/home/static/home/maps.mjs';

test('location payload is rounded to about one kilometre', () => {
  assert.deepEqual(pointPayload(-6.36789, 106.82345), {lat:-6.37, lon:106.82});
});
test('region payload sends only the trimmed region', () => {
  assert.deepEqual(regionPayload({region:{value:' Depok '}, lat:{value:'-6.3'}}), {region:'Depok'});
});
test('unknown points stay unknown instead of becoming coordinates zero zero', () => {
  assert.equal(validPoint(null,null), false);
  assert.equal(validPoint(NaN,106), false);
  assert.equal(validPoint(-7.2,107.9), true);
  const rows = rankedPlaces([{name:'Unknown',lat:null,lon:null}, {name:'Known',lat:-7.2,lon:107.9}],[-7.2,107.9]);
  assert.equal(rows[0].name,'Known'); assert.equal(rows[1].distance,null);
});
test('distance is straight-line and does not mutate source data', () => {
  assert.equal(distanceKm([-7.2,107.9],[-7.2,107.9]),0);
  const source = [{name:'B',lat:-7.21,lon:107.91},{name:'A',lat:-7.2,lon:107.9}];
  assert.equal(rankedPlaces(source,[-7.2,107.9])[0].name,'A');
  assert.equal(source[0].name,'B'); assert.ok(!('distance' in source[0]));
});
test('external links reject script URLs and unknown-point search is encoded', () => {
  assert.equal(safeURL('javascript:alert(1)'),null); assert.equal(safeURL('http://example.com'),null);
  assert.ok(placeLink({name:'<img onerror=alert(1)>',address:'Depok',lat:null,lon:null}).includes('%3Cimg'));
});

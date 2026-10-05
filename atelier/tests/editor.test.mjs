import {test} from 'node:test';
import assert from 'node:assert/strict';
import {filterPosts} from '../assets/data.mjs';
import {previewDiff} from '../assets/editor.mjs';
import {readFileSync} from 'node:fs';
test('filters retain post identity and media',()=>{const posts=[{key:'a',week:'w1',platform:'X'},{key:'b',week:'w1',platform:'Threads'},{key:'c',week:'w2',platform:'X'}];assert.deepEqual(filterPosts(posts,'w1','X'),[posts[0]]);assert.equal(filterPosts(posts,'','').length,3);});
test('diff includes before and after without changing source',()=>{const before={content:'before',quote:'same'},after={content:'after',quote:'same'};const diff=previewDiff(before,after);assert.match(diff,/− "before"/);assert.match(diff,/＋ "after"/);assert.doesNotMatch(diff,/quote/);assert.equal(before.content,'before');assert.equal(previewDiff(before,before),'変更なし');});
test('A/B are in one grid, C is separate third; output uses textContent',()=>{const css=readFileSync(new URL('../assets/style.css',import.meta.url),'utf8');assert.match(css,/repeat\(2,minmax/);assert.match(css,/nth-child\(3\)/);const data=readFileSync(new URL('../assets/data.mjs',import.meta.url),'utf8');assert.match(data,/textContent=text/);});

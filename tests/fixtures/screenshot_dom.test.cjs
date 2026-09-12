// Characterize our screenshot DOM, not a browser's broader selector grammar.
const assert = require('node:assert/strict');
const test = require('node:test');
const {createDOM} = require('./screenshot_dom.cjs');

function fixture() {
  const dom = createDOM({tag: 'document', attrs: {}, children: []});
  const {document, Element} = dom;
  const body = document.appendChild(new Element('body', {id: 'body', class: 'outside'}));
  const root = body.appendChild(new Element('section', {id: 'root', class: 'scope'}));
  const branch = root.appendChild(new Element('div', {id: 'branch', class: 'branch'}));
  const deep = branch.appendChild(new Element('button', {
    id: 'deep', class: 'pick active', 'data-kind': 'primary', 'aria-label': 'Deep choice'
  }));
  deep.textContent = 'Choice';
  branch.appendChild(new Element('input', {id: 'checked', class: 'pick', type: 'checkbox', checked: ''}));
  const text = root.appendChild(new Element('p', {id: 'text'}));
  text.textContent = 'Text';
  root.appendChild(new Element('div', {id: 'empty'}));
  root.appendChild(new Element('button', {id: 'direct', class: 'pick'}));
  const other = body.appendChild(new Element('aside', {id: 'other'}));
  other.appendChild(new Element('button', {id: 'outside-pick', class: 'pick'}));
  return {...dom, root, branch, deep};
}
const ids = nodes => nodes.map(node => node.id);

test('native select options and moving rows preserve the current tree', () => {
  const {document, Element, root, branch, deep} = fixture();
  root.appendChild(deep);
  assert.equal(branch.contains(deep), false);
  root.insertBefore(deep, null);
  assert.equal(root.lastChild, deep);
  assert.equal(root.querySelectorAll('#deep').length, 1);
  deep.remove();
  assert.equal(document.getElementById('deep'), null);
  const select = root.appendChild(new Element('select'));
  const group = select.appendChild(new Element('optgroup'));
  group.appendChild(new Element('option', {value: 'one'}));
  group.appendChild(new Element('option', {value: 'two'}));
  assert.equal(select.options.length, 2);
  assert.equal(select.selectedIndex, 0);
  assert.equal(select.value, 'one');
  select.value = 'two';
  assert.equal(select.selectedIndex, 1);
  select.textContent = '';
  assert.equal(select.value, '');
  assert.equal(select.selectedIndex, -1);
});

// Literal order catches breadth-first walks, branch pruning, root inclusion,
// selector-list duplication, and changed ancestor/combinator matching.
for (const [selector, expected] of [
  ['*', ['branch', 'deep', 'checked', 'text', 'empty', 'direct']],
  ['button', ['deep', 'direct']],
  ['#deep', ['deep']],
  ['.pick', ['deep', 'checked', 'direct']],
  ['button.pick.active', ['deep']],
  ['[data-kind]', ['deep']],
  ['[data-kind="primary"]', ['deep']],
  ['[data-kind="secondary"]', []],
  ['[aria-label="Deep choice"]', ['deep']],
  ['input[type="checkbox"]:checked', ['checked']],
  ['div:not(:empty)', ['branch']],
  ['p:not(:empty)', ['text']],
  ['button:not(:empty)', ['deep']],
  ['.scope .pick', ['deep', 'checked', 'direct']],
  ['.outside .pick', ['deep', 'checked', 'direct']],
  ['.outside > .scope .branch > button', ['deep']],
  ['.scope > button', ['direct']],
  ['.scope > button:last-child', ['direct']],
  ['.branch > button:last-child', []],
  ['.branch > input:last-child', ['checked']],
  ['.branch > .pick', ['deep', 'checked']],
  ['.missing .pick', []],
  ['.pick button', []],
  ['#direct, .pick, #deep', ['deep', 'checked', 'direct']],
  ['#root', []],
  ['.scope', []],
  ['#missing', []],
]) {
  test('selector order and scope: ' + selector, () => {
    const {root} = fixture();
    assert.deepEqual(ids(root.querySelectorAll(selector)), expected);
    const first = root.querySelector(selector);
    if (expected.length) assert.equal(first.id, expected[0]);
    else assert.equal(first, null);
  });
}

test('selector state reflects property and attribute changes', () => {
  const {document, root, deep} = fixture();
  const checked = document.getElementById('checked');
  checked.checked = false;
  assert.deepEqual(ids(root.querySelectorAll(':checked')), []);
  checked.checked = true;
  checked.type = 'radio';
  assert.deepEqual(ids(root.querySelectorAll('input[type="radio"]:checked')), ['checked']);
  assert.deepEqual(ids(root.querySelectorAll('input[type="checkbox"]')), []);
  deep.classList.remove('active');
  deep.setAttribute('data-kind', 'secondary');
  assert.deepEqual(ids(root.querySelectorAll('.active, [data-kind="primary"]')), []);
  assert.deepEqual(ids(root.querySelectorAll('[data-kind="secondary"]')), ['deep']);
  deep.removeAttribute('data-kind');
  deep.textContent = '';
  assert.deepEqual(ids(root.querySelectorAll('[data-kind], button:not(:empty)')), []);
});

test('queries see insertion, removal, ID changes and replacement without cached results', () => {
  const {document, root, branch, deep} = fixture();
  assert.equal(document.getElementById('new'), null);
  const saved = root.querySelectorAll('.pick');
  const added = document.createElement('button');
  added.id = 'new'; added.className = 'pick';
  root.prepend(added);
  const middle = document.createElement('button');
  middle.setAttribute('id', 'middle'); middle.className = 'pick';
  root.insertBefore(middle, document.getElementById('direct'));
  assert.deepEqual(ids(root.querySelectorAll('.pick')), ['new', 'deep', 'checked', 'middle', 'direct']);
  assert.equal(document.getElementById('new'), added);
  assert.deepEqual(ids(saved), ['deep', 'checked', 'direct']);
  saved.length = 0;
  assert.deepEqual(ids(root.querySelectorAll('.pick')), ['new', 'deep', 'checked', 'middle', 'direct']);
  root.removeChild(branch);
  assert.equal(document.getElementById('deep'), null);
  assert.deepEqual(ids(root.querySelectorAll('.pick')), ['new', 'middle', 'direct']);
  root.appendChild(branch);
  assert.equal(document.getElementById('deep'), deep);
  assert.deepEqual(ids(root.querySelectorAll('.pick')), ['new', 'middle', 'direct', 'deep', 'checked']);
  added.setAttribute('id', 'renamed');
  assert.equal(document.getElementById('new'), null);
  assert.equal(document.getElementById('renamed'), added);
  added.id = 'again';
  assert.equal(document.getElementById('renamed'), null);
  assert.equal(document.getElementById('again'), added);
  root.innerHTML = '';
  assert.deepEqual(root.querySelectorAll('*'), []);
  assert.equal(document.getElementById('deep'), null);
  const replacement = document.createElement('button');
  replacement.id = 'deep'; replacement.className = 'pick';
  root.appendChild(replacement);
  assert.deepEqual(ids(root.querySelectorAll('.pick')), ['deep']);
  assert.equal(document.getElementById('deep'), replacement);
  assert.notEqual(document.getElementById('deep'), deep);
  root.textContent = 'Replaced again';
  assert.equal(document.getElementById('deep'), null);
});

test('ID lookup excludes document itself and returns the first duplicate in preorder', () => {
  const {document, root, deep, Element} = fixture();
  document.id = 'document-only';
  assert.equal(document.getElementById('document-only'), null);
  deep.id = 'duplicate';
  const later = root.appendChild(new Element('button', {id: 'duplicate'}));
  assert.equal(document.getElementById('duplicate'), deep);
  const earlier = new Element('button', {id: 'duplicate'});
  root.prepend(earlier);
  assert.equal(document.getElementById('duplicate'), earlier);
  root.removeChild(root.firstChild);
  deep.parentNode.removeChild(deep);
  assert.equal(document.getElementById('duplicate'), later);
  root.removeChild(later);
  assert.equal(document.getElementById('duplicate'), null);
});

test('closest and contains retain self inclusion and real ancestry', () => {
  const {document, root, branch, deep} = fixture();
  assert.equal(deep.closest('.pick'), deep);
  assert.equal(deep.closest('.scope'), root);
  assert.equal(deep.closest('.outside').id, 'body');
  assert.equal(deep.closest('.missing'), undefined);
  assert.equal(root.contains(root), true);
  assert.equal(root.contains(deep), true);
  assert.equal(root.contains(document.getElementById('outside-pick')), false);
  root.removeChild(branch);
  assert.equal(root.contains(deep), false);
  assert.equal(deep.closest('.scope'), null);
});

test('single selector tests each descendant once, not once per ancestor', () => {
  const {document, Element} = createDOM({tag: 'document', attrs: {}, children: []});
  const a = document.appendChild(new Element('div', {id: 'a'}));
  const b = a.appendChild(new Element('div', {id: 'b'}));
  const c = b.appendChild(new Element('div', {id: 'c'}));
  const d = c.appendChild(new Element('div', {id: 'd'}));
  const e = document.appendChild(new Element('div', {id: 'e'}));
  const visits = [];
  for (const node of [a, b, c, d, e]) {
    const matches = node.matches;
    node.matches = function(selector) { visits.push(this.id); return matches.call(this, selector); };
  }
  assert.deepEqual(ids(document.querySelectorAll('*')), ['a', 'b', 'c', 'd', 'e']);
  assert.deepEqual(visits, ['a', 'b', 'c', 'd', 'e']);
});

test('ID lookup stops before expanding the first match or later branches', () => {
  const {document, root, deep} = fixture();
  const expanded = [];
  for (const node of [deep, document.getElementById('other')]) {
    const children = node.children;
    Object.defineProperty(node, 'children', {get() { expanded.push(node.id); return children; }});
  }
  assert.equal(document.getElementById('deep'), deep);
  assert.deepEqual(expanded, []);
  assert.equal(document.getElementById('missing'), null);
  assert.ok(expanded.includes('deep'));
  assert.ok(expanded.includes('other'));
  assert.equal(root.querySelector('#deep'), deep);
});

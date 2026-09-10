// The screenshot harness's deliberately small DOM subset. A factory keeps
// document focus and recorded scrolls local to each page, including in tests.
const assert = require('node:assert/strict');

// Preorder over current children, excluding the root. A true visit result
// stops before expanding that node — ID lookup must not scan later branches.
function visitDescendants(root, visit) {
  for (const child of root.children) {
    if (visit(child) || visitDescendants(child, visit)) return true;
  }
  return false;
}

function createDOM(page) {
  const scrolls = [];
  class Element {
    constructor(tag, attrs = {}) {
      this.tagName = tag.toUpperCase(); this.attrs = {...attrs};
      this.id = attrs.id || ''; this.className = attrs.class || '';
      this.children = []; this.listeners = {}; this.style = {};
      this.value = attrs.value || ''; this.hidden = 'hidden' in attrs;
      this.disabled = 'disabled' in attrs; this.checked = 'checked' in attrs;
      this.dataset = Object.fromEntries(Object.entries(attrs).filter(([k]) => k.startsWith('data-'))
        .map(([k, v]) => [k.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase()), v]));
    }
    appendChild(el) { this.children.push(el); el.parentNode = this; return el; }
    prepend(el) { this.children.unshift(el); el.parentNode = this; }
    insertBefore(el, before) { this.children.splice(this.children.indexOf(before), 0, el); el.parentNode = this; }
    removeChild(el) { this.children.splice(this.children.indexOf(el), 1); el.parentNode = null; return el; }
    get firstChild() { return this.children[0] || null; }
    get firstElementChild() { return this.firstChild; }
    get nextSibling() { return this.parentNode?.children[this.parentNode.children.indexOf(this) + 1] || null; }
    get previousElementSibling() { return this.parentNode?.children[this.parentNode.children.indexOf(this) - 1] || null; }
    set textContent(text) { this.children = []; this.text = String(text); }
    get textContent() { return (this.text || '') + this.children.map(el => el.textContent).join(''); }
    set innerHTML(text) { assert.equal(text, ''); this.textContent = ''; }
    setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); }
    getAttribute(k) { return this.attrs[k] ?? null; }
    removeAttribute(k) { delete this.attrs[k]; }
    get classList() { return {
      contains: name => this.className.split(/\s+/).includes(name),
      toggle: (name, on) => {
        if (on === undefined) on = !this.classList.contains(name);
        this.className = this.className.split(/\s+/).filter(x => x && x !== name).concat(on ? [name] : []).join(' ');
      },
      add: name => this.classList.toggle(name, true), remove: name => this.classList.toggle(name, false)
    }; }
    matches(selector) {
      let s = selector;
      if (s === '*') return true;
      if (s.includes(':not(:empty)')) { if (!this.children.length && !this.text) return false; s = s.replace(':not(:empty)', ''); }
      if (s.includes(':checked')) { if (!this.checked) return false; s = s.replace(':checked', ''); }
      const attributes = [...s.matchAll(/\[([\w-]+)(?:="([^"]*)")?\]/g)];
      if (!attributes.every(m => m[2] === undefined ? this.getAttribute(m[1]) !== null
        : (m[1] === 'type' ? this.type || this.getAttribute('type') : this.getAttribute(m[1])) === m[2])) return false;
      s = s.replace(/\[[^\]]+\]/g, '');
      const id = s.match(/#([\w-]+)/); if (id && this.id !== id[1]) return false;
      if (![...s.matchAll(/\.([\w-]+)/g)].every(m => this.classList.contains(m[1]))) return false;
      const tag = s.match(/^[\w-]+/); return !tag || this.tagName.toLowerCase() === tag[0];
    }
    querySelectorAll(selector) {
      const results = [];
      visitDescendants(this, el => {
        if (selector.split(',').some(part => {
          const chain = part.trim().split(/\s+(?![^\[]*\])/);
          let node = el;
          if (!node.matches(chain.pop())) return false;
          while (chain.length) {
            const parent = chain.pop();
            if (parent === '>') { node = node.parentNode; if (!node || !node.matches(chain.pop())) return false; }
            else { node = node.parentNode; while (node && !node.matches(parent)) node = node.parentNode; if (!node) return false; }
          }
          return true;
        })) results.push(el);
      });
      return results;
    }
    querySelector(s) { return this.querySelectorAll(s)[0] || null; }
    closest(s) { let el = this; while (el && !el.matches(s)) el = el.parentNode; return el; }
    contains(el) { return el === this || this.querySelectorAll('*').includes(el); }
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
    removeEventListener(name, callback) { this.listeners[name] = (this.listeners[name] || []).filter(x => x !== callback); }
    dispatchEvent(event) {
      event.target ||= this; event.preventDefault ||= () => {}; event.stopPropagation ||= () => {};
      (this.listeners[event.type] || []).forEach(callback => callback(event));
    }
    click() { if (!this.disabled) this.dispatchEvent({type: 'click'}); }
    focus() { document.activeElement = this; }
    scrollIntoView(options) { scrolls.push({element: this, options}); }
    getBoundingClientRect() { return {width: 400, height: 240, top: 0, bottom: 240, left: 0, right: 400}; }
  }
  function build(node) { const el = new Element(node.tag, node.attrs); node.children.forEach(child => el.appendChild(build(child))); return el; }
  const document = build(page);
  document.readyState = 'complete'; document.body = document.querySelector('body');
  document.getElementById = id => {
    let found = null;
    visitDescendants(document, el => {
      if (el.id !== id) return false;
      found = el;
      return true;
    });
    return found;
  };
  document.createElement = tag => new Element(tag);
  document.createElementNS = (_, tag) => new Element(tag);
  return {document, Element, scrolls};
}

module.exports = {createDOM};

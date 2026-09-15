/* Upload panel, status strip, and the modal dialog layer.
 *
 * The panel owns no upload logic: it collects the fields, hands them to
 * start_upload, and renders what comes back. Every guard, warning, and
 * confirmation is still composed in Python (start_upload,
 * delete_selected, format_upload_confirm) and merely rendered here — a
 * page-side confirmation would be a second copy of that text with nothing
 * keeping the two in step.
 */
(function () {
  'use strict';
  var WM = window.WM;

  // Privacy and category are NOT held here and are NOT sent. They are
  // settings, and start_upload reads them from Python's own state — the
  // page cannot hold a stale copy of a value it never holds.

  // ---- selection-dependent copy ---------------------------------------
  // Asked of Python rather than recomputed here. Both strings are pure,
  // tested functions whose decisions are subtle enough that a JavaScript
  // twin would drift within a release: the summary's "+" appears only when
  // a probe is outstanding and never on size, and the title hint discloses
  // that build_body numbers a batch -- added in 2.2.0 after users got ten
  // differently-named public videos. The round trip is in-process and
  // fires on a human click, so its cost is invisible.
  var panelSeq = 0;

  function refreshPanelText() {
    var seq = ++panelSeq;
    WM.send('panel_text', WM.list.selectedIds(), WM.el('f-stitch').checked)
      .then(function (text) {
        // Clicks can outrun replies; only the newest answer may paint, or a
        // slow earlier reply overwrites a newer count.
        if (seq !== panelSeq || !text) return;
        WM.el('selection-summary').textContent = text.summary;
        WM.el('lab-title').textContent = text.title_hint;
      });
  }
  document.addEventListener('wm:selection', refreshPanelText);
  // Stitching collapses a batch into ONE video, so the numbering
  // disclosure must appear and disappear with this checkbox too -- and the
  // tick also drives the Stitch locally button's visibility, so this runs
  // the same synchronous refresh the selection events run. Selection
  // events alone would repeat the first-cut bug where ticking a box
  // showed nothing until the selection next changed.
  // (refreshPanelText is deliberately not enough: it paints on an async
  // round trip, and a button showing a round trip late is the flash U4
  // already ruled out for the summary above.)
  function refreshOnTick() {
    refreshPanelText();
    refreshEnabled();
  }
  WM.el('f-stitch').addEventListener('change', refreshOnTick);

  // ---- what can act, and what cannot -----------------------------------
  // X1 execution, through S1's WM.setEnabled. The rule in its comment is
  // that a control is inert when the app ALREADY KNOWS the action cannot
  // be carried out from the state it is holding -- not when it might fail
  // once attempted -- and that nothing may disable the only route back out
  // of the state that disabled it. Both apply here:
  //
  //   Upload    needs at least one selected recording (Uploader 1). It was
  //             full-strength accent with a glow and nothing to do, while
  //             the blocker whispered from the foot of the card above it.
  //   Stitch    is meaningless below two selected. Disabled, NOT hidden --
  //             see the note beside it in index.html.
  //   the list  is not disabled by any of this: selecting a row is the way
  //             out of every state above, so it must stay live.
  //
  // Nothing here disables Delete: it acts on a selection too, but it lives
  // in the list footer beside Select all / Select none, and list.js owns
  // it for the same reason it owns those.
  function refreshEnabled() {
    var selected = WM.list.selectedIds().length;
    var rows = WM.list.rowCount();

    // Uploader 13. The panel used to be identical with an empty folder --
    // live fields, accent Upload, nothing acknowledging there was nothing
    // to act on -- so the empty and full states read as the same product
    // in the wrong direction. An empty folder is a fact about the folder,
    // so it is stated once and the note is the whole of the treatment.
    //
    // Title and Description stay LIVE, deliberately. S1's rule disables a
    // control when the action cannot be carried out, and typing a title is
    // an action that can -- the same reading that keeps the Previews
    // keybinds live under Settings 1 (recording a keybind for later is
    // still recording it). Upload is already inert here through the
    // selection test below, because an empty folder has nothing selected
    // in it, so nothing needs a second predicate for the empty case.
    var empty = rows === 0;
    WM.el('panel-empty-note').hidden = !empty;

    // U4. The summary's empty rendering ("Nothing selected") duplicated
    // the disabled Upload button directly below it, in two treatments for
    // one fact. Hidden here rather than in refreshPanelText, which is
    // asynchronous: the button's greying and this line would otherwise
    // settle a round trip apart and the empty state would flash.
    WM.el('selection-summary').hidden = selected === 0;

    WM.setEnabled('btn-upload', selected > 0);
    WM.setEnabled('f-stitch', selected > 1);
    // The stitch hint is gone entirely (round 3, finding 3 -- see the note
    // where it used to live in index.html). The greyed-out label below is
    // the whole of the explanation now.
    WM.el('lab-stitch').classList.toggle('disabled', selected < 2);
    // A box left ticked while its control is inert would still be read by
    // start_upload's caller below, so the checked state has to follow.
    if (selected < 2) WM.el('f-stitch').checked = false;

    // Stitch locally is visible only while the stitch checkbox is ticked
    // (which itself needs two selected). Hidden rather than disabled:
    // with the box unticked there is no action waiting to be unlocked,
    // there is nothing at all. The single-selection lane is the clip
    // editor below, which owns its own visibility.
    WM.el('btn-stitch-local').hidden = !WM.el('f-stitch').checked;
    WM.setEnabled('btn-stitch-local', selected > 1);
  }
  document.addEventListener('wm:selection', refreshEnabled);

  // ---- actions -------------------------------------------------------
  // Upload still sends unconditionally, even though refreshEnabled above
  // disables it with an empty selection. The guard and the disabled state
  // are not redundant: "select at least one video to upload" is composed
  // in Python (start_upload's _alert) and a page-side early return would
  // silently swallow it, and the button can be reached by a keyboard or a
  // stale render in the window between a selection changing and the event
  // landing. The disabled attribute is what the user reads; the Python
  // message is what they get if they arrive anyway.
  WM.el('btn-upload').addEventListener('click', function () {
    // Three arguments beyond the fields. The combat-log checkbox is gone
    // (Uploader 8) and start_upload's `logs` parameter went with it in the
    // same commit; logs are unconditional and a configured webhook is what
    // decides the post.
    WM.send('start_upload',
            WM.el('f-title').value,
            WM.el('f-desc').value,
            WM.el('f-stitch').checked,
            WM.list.selectedIds());
  });

  // Stitch locally: the joined file is KEPT in the recording folder,
  // nothing uploads, and the originals are untouched. Sends
  // unconditionally like Upload -- "an upload is already in progress" is
  // Python's sentence, and a page-side early return would swallow it.
  WM.el('btn-stitch-local').addEventListener('click', function () {
    WM.send('stitch_locally', WM.list.selectedIds());
  });

  // ---- the clip editor (exactly one selected) --------------------------
  // The single-selection lane: preview the recording, drag in/out handles
  // snapped to keyframes, cut. NOTHING here uploads -- the clip lands in
  // the recording folder as an ordinary row. Visible only while EXACTLY
  // one row is selected (the documented exception to "disabled, NOT
  // hidden": this is a context surface, like #panel-empty-note, not a
  // control being withheld). Python owns the file path -- the page asks
  // for it per selection through clip_source, the one bridge call that
  // hands a URI over, and re-asks on every change, so a stale editor
  // cannot point at a file the list no longer knows.
  var clip = {
    rowId: null, duration: 0, keys: [], noteText: '',
    markIn: 0, markOut: 0, seq: 0, degraded: false, playingSel: false,
    // The playhead is FIRST-CLASS state, not an alias of the media
    // element's currentTime: in degraded mode there is no decode to sync
    // to, and Set start / Set end must still mean something there. The
    // video updates it while playing; clicks and drags on the track move
    // it -- and seek the video too, when there is one.
    play: 0,
  };

  function clipPad(n) { return (n < 10 ? '0' : '') + n; }
  function clipFmt(t) {
    t = Math.max(0, Math.floor(t));
    var h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return h ? h + ':' + clipPad(m) + ':' + clipPad(s) : m + ':' + clipPad(s);
  }
  function clipPct(t) {
    return clip.duration > 0
      ? Math.max(0, Math.min(100, (t / clip.duration) * 100)) : 0;
  }

  function clipRender() {
    WM.el('clip-band').style.left = clipPct(clip.markIn) + '%';
    WM.el('clip-band').style.width =
      (clipPct(clip.markOut) - clipPct(clip.markIn)) + '%';
    WM.el('clip-in').style.left = clipPct(clip.markIn) + '%';
    WM.el('clip-out').style.left = clipPct(clip.markOut) + '%';
    WM.el('clip-tc-in').textContent = clipFmt(clip.markIn);
    WM.el('clip-tc-out').textContent = clipFmt(clip.markOut);
    WM.el('clip-playhead').style.left = clipPct(clip.play) + '%';
    WM.el('clip-tc-play').textContent = clipFmt(clip.play);
  }

  // Nearest keyframe at or BEFORE t: what a stream-copy cut can actually
  // deliver as a start point. The cut may begin early -- that is the
  // keyframe trade the feature accepted -- and the READOUTS show the
  // snapped value so what you see is what gets cut.
  function clipSnapIn(t) {
    var best = 0;
    for (var i = 0; i < clip.keys.length; i += 1) {
      if (clip.keys[i] <= t + 0.001) best = clip.keys[i];
      else break;
    }
    return best;
  }

  function clipSetPlay(t) {
    clip.play = Math.max(0, Math.min(t, clip.duration));
    if (!clip.degraded && clip.video) clip.video.currentTime = clip.play;
    clipRender();
  }

  function clipSetMarks(markIn, markOut) {
    clip.markIn = Math.max(0, Math.min(markIn, clip.duration));
    clip.markOut = Math.max(clip.markIn + 0.5, Math.min(markOut, clip.duration));
    clipRender();
  }

  function clipHide() {
    clip.seq += 1;  // orphan any in-flight clip_source reply
    clip.rowId = null;
    WM.el('clip-editor').hidden = true;
    // Releasing the source matters on Windows: a media element holding the
    // file open would block a rename or delete of the user's recording.
    if (clip.video) {
      clip.video.pause();
      clip.video.removeAttribute('src');
      clip.video.load();
    }
  }

  function clipShow(rowId) {
    if (clip.rowId === rowId && !WM.el('clip-editor').hidden) return;
    clipHide();
    var seq = ++clip.seq;
    clip.rowId = rowId;
    clip.video = WM.el('clip-video');
    WM.send('clip_source', rowId).then(function (src) {
      if (seq !== clip.seq || !src) return;
      if (!src.ok) { clipHide(); return; }
      clip.noteText = src.note || '';
      clip.duration = Number(src.duration) || 0;
      // A zero duration means even ffprobe could not read the file; a
      // timeline without a length is a lie, so the editor stays dark and
      // the list's own Length column already said "?".
      if (clip.duration <= 0) { clipHide(); return; }
      clip.degraded = false;
      WM.el('clip-nopreview').hidden = true;
      WM.el('clip-video').hidden = false;
      clip.markIn = 0;
      clip.markOut = clip.duration;
      WM.el('clip-video').src = src.uri;
      WM.el('clip-editor').hidden = false;
      clipRender();
      WM.send('clip_keyframes', rowId).then(function (kf) {
        if (seq !== clip.seq || !kf) return;
        clip.keys = (kf.keys || []).map(Number).filter(function (k) {
          return isFinite(k);
        });
        // First-render snapping so the default band tells the truth about
        // what a cut at 0 includes.
        clip.markIn = clipSnapIn(clip.markIn);
        clipRender();
      });
    });
  }

  // Degrade: Chromium (not FFmpeg) decodes the preview, and its stock
  // build has no HEVC. The cut NEVER depended on the picture -- drop the
  // dead element (an empty black box with controls reads as broken), show
  // Python's note, and keep the timeline working from the bridge-provided
  // duration.
  WM.el('clip-video').addEventListener('error', function () {
    if (WM.el('clip-editor').hidden) return;
    clip.degraded = true;
    WM.el('clip-video').hidden = true;
    var note = WM.el('clip-nopreview');
    note.textContent = clip.noteText || '';
    note.hidden = !note.textContent;
  });

  // Track interactions: one pointer model for both handles. Clicking the
  // track (not a handle) seeks the preview.
  (function () {
    var track = WM.el('clip-track');
    var dragging = null;
    var scrubbing = false;

    function trackTime(ev) {
      var rect = track.getBoundingClientRect();
      var frac = (ev.clientX - rect.left) / Math.max(1, rect.width);
      return Math.max(0, Math.min(1, frac)) * clip.duration;
    }

    function onMove(ev) {
      if (!dragging) return;
      var t = trackTime(ev);
      if (dragging === 'in') {
        // The in marker SNAPS DOWN to the nearest keyframe live, so the
        // band during the drag is the cut the button will make.
        var snapped = clipSnapIn(t);
        clipSetMarks(snapped, Math.max(clip.markOut, snapped + 0.5));
      } else {
        clipSetMarks(clip.markIn, t);
      }
      ev.preventDefault();
    }

    function onUp(ev) {
      if (!dragging) return;
      dragging = null;
      document.removeEventListener('pointermove', onMove);
      document.removeEventListener('pointerup', onUp);
      if (ev) ev.preventDefault();
    }

    WM.el('clip-in').addEventListener('pointerdown', function (ev) {
      dragging = 'in';
      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
      ev.preventDefault();
    });
    WM.el('clip-out').addEventListener('pointerdown', function (ev) {
      dragging = 'out';
      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
      ev.preventDefault();
    });
    // Left-click (and press-drag) on the track SCRUBS: the playhead is
    // first-class state, so this works with no decode at all -- which is
    // what makes Set start / Set end meaningful in degraded mode, where
    // they used to read a dead element and always answered 0.
    track.addEventListener('pointerdown', function (ev) {
      if (clip.duration <= 0) return;
      if (ev.target.classList && ev.target.classList.contains('clip-handle')) {
        return;  // handles run their own drag
      }
      scrubbing = true;
      track.setPointerCapture(ev.pointerId);
      clipSetPlay(trackTime(ev));
      ev.preventDefault();
    });
    track.addEventListener('pointermove', function (ev) {
      if (!scrubbing) return;
      clipSetPlay(trackTime(ev));
      ev.preventDefault();
    });
    track.addEventListener('pointerup', function () {
      scrubbing = false;
    });
    track.addEventListener('pointercancel', function () {
      scrubbing = false;
    });
  }());

  // While the preview plays, the element drives the playhead state; the
  // track's own pointer handlers own it while scrubbing.
  WM.el('clip-video').addEventListener('timeupdate', function () {
    if (WM.el('clip-editor').hidden || clip.degraded) return;
    var v = WM.el('clip-video');
    clip.play = v.currentTime;
    clipRender();
    if (clip.playingSel && v.currentTime >= clip.markOut) {
      clip.playingSel = false;
      v.pause();
    }
  });

  WM.el('btn-clip-set-in').addEventListener('click', function () {
    clipSetMarks(clipSnapIn(clip.play), clip.markOut);
  });
  WM.el('btn-clip-set-out').addEventListener('click', function () {
    clipSetMarks(clip.markIn, clip.play);
  });
  WM.el('btn-clip-play-sel').addEventListener('click', function () {
    if (clip.degraded || !clip.video) return;
    clip.playingSel = true;
    clip.video.currentTime = clip.markIn;
    clip.video.play();
  });

  WM.el('btn-cut-clip').addEventListener('click', function () {
    // Sends unconditionally like Upload: "too short", "an upload is
    // running", a stale row -- every refusal is a Python sentence, and a
    // page-side early return would swallow it.
    WM.send('cut_clip', clip.rowId, clip.markIn, clip.markOut);
  });

  // The editor lives on the selection event: a different selection count
  // hides it, exactly-one re-arms it for that row, and re-selecting the
  // SAME row keeps everything as it was.
  document.addEventListener('wm:selection', function () {
    var ids = WM.list.selectedIds();
    if (ids.length === 1) clipShow(ids[0]);
    else clipHide();
  });
  // Leaving the route must not leave the file playing in a hidden panel.
  document.addEventListener('wm:route', function () {
    if (clip.video && !clip.degraded) clip.video.pause();
    clip.playingSel = false;
  });

  WM.el('btn-retry').addEventListener('click', function () {
    WM.send('retry');
  });

  // ---- the standalone combat-log post ---------------------------------
  // Combat logs are otherwise the tail of an upload, so the only way to
  // send them was to publish a video. This is the fight that was not
  // recorded, or was recorded and is not worth uploading.
  //
  // Sends unconditionally, like Open folder and Delete selected, and for
  // the reason list.js states twice: every refusal -- no webhook, a
  // webhook that will not parse, no Gamelogs folder, no logs in the hour,
  // a Discord rejection -- is a specific sentence composed in Python, and
  // a page-side early return would swallow the one that says why nothing
  // was posted.
  //
  // In particular this is NOT gated on the webhook the note above it
  // describes. Nothing pushes a settings payload, and the only refresh is
  // this page's own get_settings call, made at load and then only when the
  // list comes back empty -- so a user who configures a webhook with
  // recordings on screen never triggers one. A button disabled on that
  // stale fact would stay dead until the next launch, which is precisely
  // what WM.setEnabled's rule forbids.
  WM.el('btn-post-logs').addEventListener('click', function () {
    WM.send('post_recent_logs');
  });

  // The one state the page cannot work out for itself, so Python pushes
  // it: a post is running, and a second one must not start on top of it.
  // Python re-states it on every call AND on every list rebuild, because
  // a push lost into a hidden window (which _push swallows) would leave
  // this button drawn as disabled -- and a disabled button cannot be
  // clicked to ask for its own repair.
  WM.handle('onLogPostRunning', function (p) {
    WM.setEnabled('btn-post-logs', !p.running);
  });

  // D5. Cancel and Retry share the one slot beside Upload and are never
  // live together: Python arms exactly one of them, and each of its own
  // handlers below turns the other off implicitly by never being on at the
  // same time. The click sends and returns -- everything the user then
  // sees (how many of the batch made it, that they are still on the
  // channel) is composed in Python where the stop is actually noticed,
  // because the page cannot know how far the upload had got.
  WM.el('btn-cancel').addEventListener('click', function () {
    // Disabled, not hidden, the instant it is clicked: the stop is only
    // noticed at the next 4 MiB chunk boundary, so there is a real window
    // in which a second click would do nothing and look ignored.
    WM.el('btn-cancel').disabled = true;
    WM.send('cancel_upload');
  });

  // ---- the no-webhook fact --------------------------------------------
  // This used to gate a checkbox. There is no checkbox now (Uploader 8):
  // logs are posted whenever a webhook exists, so the absence of one is a
  // standing fact about the install rather than a caveat on an option, and
  // it is stated wherever it is true instead of footnoting a control the
  // maintainer read past while asking for exactly this behaviour.
  //
  // Api._post_combat_logs is silent in this case ON PURPOSE and says so:
  // with no checkbox, a "combat logs skipped" strip on a webhook-less
  // install would fire on every upload forever, which is the recurring-
  // failure pattern format_upload_confirm's docstring records as a past
  // bug. The panel carrying the fact is what makes that silence honest.
  //
  // This tests for an ABSENT webhook, not an invalid one, and the
  // difference is deliberate. Whether a stored value actually posts is
  // discord.parse_webhook's answer, and format_upload_confirm runs that
  // exact function so the dialog cannot drift from the upload -- a second
  // predicate here, in JavaScript, is the drift ui/copy.py warns about in
  // as many words. So the page states only what it can verify itself
  // (nothing is stored) and leaves "this is stored but will not parse" to
  // the confirm, which says so in Python's words. A configured-but-broken
  // webhook still earns its WARNING strip from _post_combat_logs, because
  // nothing else will tell them.
  //
  // The sentence is read off the payload rather than typed here: S3 put
  // the app's one voice for an unmet precondition in copy.py (INERT_NOTES)
  // so the two screens that need one cannot drift apart.
  document.addEventListener('wm:settings', function (ev) {
    var detail = ev.detail || {};
    var cfg = detail.settings || {};
    var notes = detail.inert_notes || {};
    var configured = String(cfg.discord_webhook || '').trim() !== '';
    var note = WM.el('logs-note');
    note.textContent = notes.no_webhook || '';
    // Empty text as well as configured: a payload without the table would
    // otherwise unhide an empty paragraph holding 8px of margin.
    note.hidden = configured || !note.textContent;
  });

  // ---- status strip ---------------------------------------------------
  var KINDS = ['FG', 'SUCCESS', 'WARNING', 'ERROR'];

  // The strip is global chrome, and app.js deliberately never tells Python
  // which route is showing, so the page cannot work out on its own whether
  // what the strip holds is still true. Round 3's finding 14 is what that
  // costs: a green `Posted combatlogs-2026-08-24_21-54.zip (15 KB).` and a
  // bar at 100% were still on screen in a capture of a DIFFERENT folder
  // with zero recordings, and again on the Profiles and Skills routes. The
  // completion state of one upload outlived everything it described.
  //
  // `busy` on every strip payload is the missing fact, and Python is the
  // only place that has it (ui/api.py, _status / _progress). A RESULT is
  // cleared when the route changes; something STILL RUNNING never is,
  // because during an upload the strip is the only feedback there is
  // (finding 12) and a stitch can go minutes between pushes -- blanking it
  // there would leave the app looking idle mid-job.
  var stripBusy = false;

  // Read off the markup, not retyped: index.html carries the word and the
  // paragraph explaining why the resting text is `Idle` and not `Ready`.
  var IDLE = WM.el('status').textContent;

  function setStatus(text, kind) {
    var node = WM.el('status');
    node.textContent = text;
    node.className = KINDS.indexOf(kind) === -1 ? 'FG' : kind;
    node.title = text;   // the strip ellipsises a long ffmpeg error
  }

  function resetStrip() {
    if (stripBusy) return;
    setStatus(IDLE, 'FG');
    WM.el('track').classList.remove('indeterminate');
    // Back to the markup's resting state: the track HIDDEN (G1), no inline
    // transform, and an EMPTY percentage rather than `0%`, which would read as
    // a stalled job.
    WM.el('track').hidden = true;
    WM.el('bar').style.transform = '';
    WM.el('pct').textContent = '';
  }

  document.addEventListener('wm:route', resetStrip);

  WM.handle('onStatus', function (p) {
    stripBusy = !!p.busy;
    setStatus(p.text || '', p.kind);
  });

  WM.handle('onProgress', function (p) {
    stripBusy = !!p.busy;
    var track = WM.el('track'), bar = WM.el('bar'), pct = WM.el('pct');
    var value = 0;
    if (p.mode === 'indeterminate') {
      // A stitch reports no readable percentage. The bar must say
      // "working" without claiming one, so the number is blanked too.
      track.classList.add('indeterminate');
      bar.style.transform = '';
      pct.textContent = '';
    } else {
      track.classList.remove('indeterminate');
      value = Math.max(0, Math.min(100, Number(p.pct) || 0));
      bar.style.transform = 'scaleX(' + (value / 100) + ')';
      pct.textContent = Math.round(value) + '%';
    }
    // G1: the track is drawn only while there is a job to report. A push
    // that reports a POSITION shows it -- an animating stitch, any real
    // percentage, and the deliberate 0% api.py sends when a stitch finishes
    // and the upload phase begins (`_progress(0.0, busy=True)`, inside the
    // `if job.stitch:` branch), where an empty groove is correct because it
    // is about to move. A plain upload has no such push; its first is a
    // real percentage from on_progress.
    //
    // TWO pushes arrive at 0% with nothing running, and both put the bar
    // away rather than drawing an empty groove:
    //
    //   - the error path (`_progress(0.0, busy=False)`), which exists to
    //     STOP the indeterminate animation rather than to claim a position.
    //     Its real occupant is a stitch failure -- an exhausted retry
    //     raises UploadFailed and pushes no progress at all, so the bar
    //     there keeps its last percentage.
    //   - a Cancel taken before the first chunk callback. Both cancel
    //     paths push `_progress(self._last_pct, ..., busy=False)`, and
    //     `_last_pct` is 0.0 until on_progress first writes it.
    //
    // The cancel case does NOT contradict api.py's "the bar keeps the
    // ground the job actually covered rather than resetting to 0". That
    // rule is about not throwing away ground already covered, and it still
    // holds -- any non-zero `_last_pct` is a position and still shows. When
    // the ground covered is zero there is nothing for the bar to keep, and
    // the strip's own sentence says `0 of 1`. Leaving an empty groove there
    // would be G1's defect in a state a user can reach.
    //
    // A finished job keeps its bar: 100% is a position, and round 3's
    // finding 14 requires the result to survive until the route changes.
    //
    // The percentage goes with it. .pct is a sibling of the track, not a
    // child, so hiding one leaves the other -- and this lane's first cut
    // left a bare `0%` floating beside the error with no groove under it,
    // which is the stalled-job reading resetStrip's own comment rules out.
    // Caught in the ?dev=1 harness driving api.py's real pushes; the suite
    // renders nothing and could not have seen it.
    var show = p.mode === 'indeterminate' || value > 0 || stripBusy;
    track.hidden = !show;
    if (!show) pct.textContent = '';
    if (p.text) setStatus(p.text, p.kind);
  });

  WM.handle('onRetryAvailable', function (p) {
    WM.el('btn-retry').disabled = !p.available;
  });

  // Cancel takes Retry's place in the slot while a job is running, and
  // hands it back when the job ends. Hidden rather than disabled, and
  // Retry hidden while it shows: an inert Cancel beside an inert Retry is
  // two dead controls describing states the panel is not in. Re-enabled
  // on every arming so a previous job's click cannot leave it dead.
  WM.handle('onCancelAvailable', function (p) {
    var on = !!p.available;
    WM.el('btn-cancel').hidden = !on;
    WM.el('btn-cancel').disabled = false;
    WM.el('btn-retry').hidden = on;
  });

  // Round 3, finding 5, the panel half. The strip says the upload
  // succeeded (L7's _upload_summary), and the panel used to contradict it:
  // the same `1 selected · 108.8 MB · 0:17:07` above the same saturated
  // Upload button, so the post-success screen was near-identical to the
  // pre-upload armed screen and the only other evidence was a 14px grey
  // arrow in the narrowest column.
  //
  // Clearing the selection is what makes the screen change, and it is
  // honest rather than cosmetic: those recordings are up, the row now
  // carries its link, and re-sending the same files is not the next
  // action. The summary falls back to "Nothing selected" and Upload goes
  // inert through refreshEnabled, both by the existing path.
  //
  // The page clears it, not Python: selection is client state and never
  // crosses the bridge (CLAUDE.md), so what arrives is the semantic event
  // -- the job finished -- and the page decides what that means for it.
  //
  // Deliberately NOT fired on a cancel: a stopped batch leaves some files
  // uploaded and some not, and clearing there would hide which is which
  // at exactly the moment that distinction matters.
  WM.handle('onUploadDone', function () {
    WM.list.clearSelection();
  });

  // ---- upload destination ---------------------------------------------
  // Rendered by Python and pushed, not composed here: format_destination
  // states the "learned from the first upload" case in words, and that
  // explanation is tested copy rather than a template.
  WM.handle('onChannel', function (p) {
    if (p.destination) WM.el('destination').textContent = p.destination;
  });

  WM.handle('onSettings', function (p) {
    if (p.destination) WM.el('destination').textContent = p.destination;
    // Settings owns the rest of this payload; it re-dispatches so both
    // modules can consume one push without either owning the handler.
    document.dispatchEvent(new CustomEvent('wm:settings', { detail: p }));
  });

  // ---- dialog layer ----------------------------------------------------
  // A queue, not a single slot: workers can push a warning and a confirm
  // in quick succession, and a second arriving dialog must not silently
  // discard the first — which for a `confirm` would strand Python waiting
  // on a dialog_response that never comes.
  var queue = [];
  var active = null;
  var returnFocus = null;
  var returnFocusOwned = false;
  var lastPageFocus = null;

  var overlay = WM.el('overlay');
  var scrimPressStarted = false;
  var dlg = WM.el('dialog');
  var btnOk = WM.el('dlg-ok');
  var btnCancel = WM.el('dlg-cancel');
  var dlgInput = WM.el('dlg-input');
  var dlgSelect = WM.el('dlg-select');
  var dlgSelectLabel = WM.el('dlg-select-label');
  var dlgSelectDetail = WM.el('dlg-select-detail');

  function compactCaption(label) {
    // Native popups size to option text, ignoring the select's CSS width.
    // This is a presentation budget, not a source-title validation limit.
    var points = label.match(/[\uD800-\uDBFF][\uDC00-\uDFFF]|[\s\S]/g) || [];
    return points.length > 44 ? points.slice(0, 43).join('') + '…' : label;
  }

  function showChoiceDetail() {
    var compact = active && active.kind === 'choice' && active.compact;
    var selected = compact && dlgSelect.options[dlgSelect.selectedIndex];
    dlgSelectDetail.hidden = !selected;
    dlgSelectDetail.textContent = selected ? selected.title : '';
    if (selected) dlgSelect.setAttribute('aria-describedby', 'dlg-select-detail');
    else dlgSelect.removeAttribute('aria-describedby');
  }
  dlgSelect.addEventListener('change', showChoiceDetail);

  // A worker may disable its trigger before its confirmation reaches the
  // page. Remember focus while the page still owns it, then fall back to an
  // enabled control on the same route if that trigger remains unavailable.
  document.addEventListener('focusin', function (ev) {
    if (overlay.contains(ev.target)) return;
    if (overlay.hidden) {
      lastPageFocus = ev.target;
    } else {
      // A newer page interaction owns focus, even if it later blurs or returns
      // to the dialog. Keep this revoked through the queue: promise continuations
      // run too late to stop next() restoring an obsolete invoker synchronously.
      returnFocusOwned = false;
    }
  });

  function show(item) {
    active = item;
    dlg.className = 'dialog ' + (item.kind || 'info');
    WM.el('dlg-title').textContent = item.title || '';
    WM.el('dlg-body').textContent = item.body || '';
    var isConfirm = item.kind === 'confirm';
    var isPrompt = item.kind === 'prompt';
    var isChoice = item.kind === 'choice';
    if (isChoice && item.compact) dlg.classList.add('compact-choice');
    dlgInput.hidden = !isPrompt;
    if (isPrompt) { dlgInput.value = item.value || ''; }
    dlgSelect.hidden = !isChoice;
    dlgSelectLabel.hidden = !isChoice;
    if (isChoice) {
      dlgSelectLabel.textContent = item.label || 'Choose';
      dlgSelect.textContent = '';
      (item.groups || []).forEach(function (group) {
        var optgroup = document.createElement('optgroup');
        optgroup.label = group.label || '';
        (group.options || []).forEach(function (option) {
          var node = document.createElement('option');
          node.value = option.value;
          var label = option.label || option.value;
          node.textContent = item.compact ? compactCaption(label) : label;
          if (item.compact) node.title = label;
          optgroup.appendChild(node);
        });
        if (optgroup.children.length) { dlgSelect.appendChild(optgroup); }
      });
    }
    showChoiceDetail();
    // Answerable dialogs need the same explicit way out.
    btnCancel.hidden = !(isConfirm || isPrompt || isChoice);
    btnOk.textContent = isConfirm
      ? (item.confirm_label || 'Confirm')
      : (isPrompt ? 'Set'
                  : (isChoice ? (item.confirm_label || 'Choose') : 'OK'));
    // The affirming button of a destructive confirm is .btn.danger, not
    // .btn.acc.
    //
    // This line used to read `isConfirm ? 'btn acc' : 'btn'` under a
    // comment saying "Upload is the app's only irreversible action, so
    // the accent stays on the affirming button of a confirm". Delete and
    // the EVE settings copy had both falsified that premise long before
    // anyone re-read it, so `Delete recording?` and `Copy X's settings
    // onto 34 other characters?` were rendering Confirm in the same
    // encouraging purple as `Upload` -- and auto-focused, so it also
    // carried the focus ring. The trigger that opens the delete dialog is
    // itself .btn.danger (index.html:112): the colour system inverted at
    // the exact moment the stakes peaked.
    //
    // Upload keeps .btn.acc. It is irreversible in the sense that a video
    // becomes public, but it destroys nothing, and it is the one action
    // the Uploader exists to perform.
    var destructive = isConfirm && !!item.destructive;
    btnOk.className = destructive
      ? 'btn danger'
      : (isConfirm ? 'btn acc' : 'btn');
    // The heading tick takes the same severity, so the dialog reads as
    // destructive before the eye reaches the button.
    if (destructive) { dlg.className = 'dialog confirm destructive'; }
    overlay.hidden = false;
    // The field, not the button: a prompt exists to be typed into, and
    // landing on OK means every user starts with a Tab. A destructive
    // confirm starts on its safe answer; Enter then follows the focused
    // native button rather than acting as a hidden second shortcut to Yes.
    if (isPrompt) {
      dlgInput.focus();
      dlgInput.select();
    } else if (isChoice) {
      dlgSelect.focus();
    } else if (destructive) {
      btnCancel.focus();
    } else {
      btnOk.focus();
    }
  }

  function enqueue(item) {
    if (active) {
      queue.push(item);
      return;
    }
    returnFocusOwned = true;
    returnFocus = document.activeElement;
    if (!returnFocus || returnFocus === document.body) {
      returnFocus = lastPageFocus;
    }
    show(item);
  }

  function focusPageControl(target) {
    if (!target || !document.contains(target) || target.disabled || !target.focus
        || !target.getClientRects().length
        || window.getComputedStyle(target).visibility !== 'visible') return false;
    target.focus();
    return document.activeElement === target;
  }

  function restorePageFocus(target) {
    if (focusPageControl(target)) return;
    // A queued answer can hide the invoker's subview. :not([hidden]) only
    // checks the control itself, so try rendered controls on the current route
    // and verify focus landed rather than stopping at a hidden sibling view.
    var route = document.querySelector('.route.active');
    if (!route) return;
    var fallback = route.querySelectorAll(
      'button:not([hidden]):not(:disabled), input:not([hidden]):not(:disabled), '
      + 'select:not([hidden]):not(:disabled), textarea:not([hidden]):not(:disabled), '
      + '[tabindex="0"]');
    for (var i = 0; i < fallback.length; i += 1) {
      if (focusPageControl(fallback[i])) return;
    }
  }

  function next() {
    active = null;
    if (queue.length) {
      show(queue.shift());
      return;
    }
    overlay.hidden = true;
    var target = returnFocus;
    var owned = returnFocusOwned;
    returnFocus = null;
    returnFocusOwned = false;
    if (owned) restorePageFocus(target);
  }

  function answer(ok) {
    if (!active) return;
    // A page-raised confirm resolves its own promise; a Python-raised one
    // answers across the bridge. Never both: Python is not waiting on a
    // dialog it did not ask for, and a spurious dialog_response would
    // answer somebody else's question.
    if (active.resolve) {
      // A prompt answers with its text, or null for cancel -- matching
      // window.prompt, so the call sites' `=== null` guards still hold.
      active.resolve(active.kind === 'prompt'
                     ? (ok ? dlgInput.value : null)
                     : (active.kind === 'choice'
                        ? (ok ? dlgSelect.value : null)
                        : ok));
    } else if (active.kind === 'confirm' && active.request_id !== undefined
               && active.request_id !== null) {
      WM.send('dialog_response', active.request_id, ok);
    }
    next();
  }

  // The page's own confirm, for a destructive action the page owns.
  //
  // Python's _confirm cannot serve these: it BLOCKS the calling thread
  // until dialog_response arrives, so it must run on a worker -- calling
  // it from a bridge method would deadlock the very thread that has to
  // deliver the answer. That is why reset_binds reached for
  // window.confirm, which WebView2 renders as browser chrome captioned
  // with the page's origin.
  //
  // Same queue, same styling, same Escape-is-No rule as a Python dialog.
  //
  // `opts.destructive` marks the affirming answer as one that destroys
  // something clicking again will not bring back; it picks .btn.danger
  // over .btn.acc. Pass it for the ACTION, not for the wording -- a
  // treatment that appears on every confirm says nothing.
  WM.confirm = function (title, body, opts) {
    return new Promise(function (resolve) {
      var item = { kind: 'confirm', title: title, body: body,
                   destructive: !!(opts && opts.destructive),
                   resolve: resolve };
      enqueue(item);
    });
  };

  // Resolves with the typed text, or null if cancelled -- the same
  // contract window.prompt had, so callers keep their `=== null` guard.
  WM.prompt = function (title, body, value) {
    return new Promise(function (resolve) {
      var item = { kind: 'prompt', title: title, body: body,
                   value: value, resolve: resolve };
      enqueue(item);
    });
  };

  WM.choose = function (title, body, groups, confirmLabel, fieldLabel, opts) {
    return new Promise(function (resolve) {
      enqueue({kind: 'choice', title: title, body: body, label: fieldLabel || 'Copy from',
               groups: groups || [], confirm_label: confirmLabel || 'Choose',
               compact: !!(opts && opts.compact), resolve: resolve});
    });
  };

  btnOk.addEventListener('click', function () { answer(true); });
  btnCancel.addEventListener('click', function () { answer(false); });
  overlay.addEventListener('mousedown', function (ev) {
    scrimPressStarted = ev.target === overlay;
  });
  overlay.addEventListener('mouseup', function (ev) {
    // Both ends must be a primary-button press on the scrim. A text-selection
    // drag that overshoots the dialog must not discard a prompt value, and a
    // context click must remain only a context click.
    var cancel = ev.button === 0
      && scrimPressStarted && ev.target === overlay;
    scrimPressStarted = false;
    if (ev.button !== 0) { return; }
    if (cancel) { answer(false); }
  });
  dlgInput.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' && active && active.kind === 'prompt') {
      ev.preventDefault();
      answer(true);
    }
  });
  dlgSelect.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' && active && active.kind === 'choice') {
      ev.preventDefault();
      answer(true);
    }
  });

  document.addEventListener('keydown', function (ev) {
    if (overlay.hidden) return;
    if (ev.key === 'Escape') {
      ev.preventDefault();
      // Escape on a confirm is a No, never a silent dismissal: Python is
      // blocked on an answer and must get one. A prompt cancels the same
      // way -- answering true would set whatever happened to be in the
      // field.
      answer(active && (active.kind === 'confirm' || active.kind === 'prompt'
                        || active.kind === 'choice') ? false : true);
    } else if (ev.key === 'Tab') {
      var focusable = dlg.querySelectorAll(
        'button:not([hidden]):not(:disabled), input:not([hidden]):not(:disabled), '
        + 'select:not([hidden]):not(:disabled)');
      if (!focusable.length) {
        ev.preventDefault();
        return;
      }
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        ev.preventDefault();
        last.focus();
      } else if (!ev.shiftKey && document.activeElement === last) {
        ev.preventDefault();
        first.focus();
      } else if (!dlg.contains(document.activeElement)) {
        ev.preventDefault();
        first.focus();
      }
    }
  }, true);

  WM.handle('onDialog', function (p) { enqueue(p); });
}());

/**
 * regression.js — exercise the builder's connection and deletion rules.
 *
 * Run it from the builder's own console:
 *
 *   fetch('tools/regression.js').then(r => r.text()).then(eval)
 *
 * It dismisses the welcome screen itself, so an untouched page is fine. Results
 * print as a table; the returned object carries the detail.
 *
 * Why it exists: every rule here was checked by hand while it was written, one
 * throwaway snippet at a time, and none of those checks survived. These are the
 * same measurements, kept. Each asserts a value rather than that nothing threw
 * — a swing's gap is 0.0000, a Play Tower is 16 sockets, a bridge locked to a
 * 5ft deck refuses a 7ft one — because "it ran" would have passed for most of
 * the bugs this suite was written from.
 *
 * The whole thing works through the app's own entry points: Item_clicked to
 * place, Trash_picked_mesh to delete, blueprint.restore to load. Nothing
 * reaches past them into internals, so a test failing means a person would have
 * seen it too.
 *
 * Everything runs against the real catalog. It leaves the yard empty.
 */
(async function () {
  "use strict";

  // ————————————————————————————————————————————————— harness

  const results = [];
  let group = "";

  const eq = (actual, expected) => JSON.stringify(actual) === JSON.stringify(expected);

  /** Record one assertion. `expected` may be a value or a predicate. */
  function check(name, actual, expected) {
    const ok = typeof expected === "function" ? !!expected(actual) : eq(actual, expected);
    results.push({ group, name, ok, actual, expected: typeof expected === "function" ? "(predicate)" : expected });
    return ok;
  }

  const suite = (name) => { group = name; };

  const fail = (name, error) =>
    results.push({ group, name, ok: false, actual: String(error), expected: "no error" });

  // ————————————————————————————————————————————————— app helpers

  const idle = (ms) => new Promise((r) => setTimeout(r, ms));

  const normal = () => {
    Mode.mode = Mode.normal;
    plug_model = null;
    plug_joint = null;
    selected_socket = null;
  };

  const placed = () => models_with_available_joints.map((m) => m.object_id).sort();

  /** Every product template, whether or not its geometry has loaded. */
  const templates = () => {
    const out = [];
    for (const category of Categories)
      for (const child of category.children || []) if (child.model) out.push(child.model);
    return out;
  };

  const template = (id) => templates().find((m) => m.object_id === id);

  /** A loaded, unplaced copy — for asking rule questions without committing. */
  const probe = async (id) => {
    const model = template(id);
    await model.ensure_loaded();
    const copy = model.clone();
    return {
      model: copy,
      joint: copy.joints[0],
      done: () => scene.remove(copy.mesh),
    };
  };

  /** A socket on `model` that is still open and offers `layer`. */
  const socketFor = (model, layer) =>
    model.sockets().find(
      (socket) =>
        Socket_is_open(socket) &&
        socket.joints.some((joint) => joint.layer === layer && joint.available)
    );

  /** Place `id` into `socket`; returns the model, or null if it was refused. */
  const place = async (socket, id) => {
    const before = models_with_available_joints.length;
    selected_socket = socket;
    selected_object_id = id;
    await Item_clicked();
    normal();
    return models_with_available_joints.length > before
      ? models_with_available_joints[models_with_available_joints.length - 1]
      : null;
  };

  /** The first model, which has no socket to go into. */
  const placeFirst = async (id) => {
    selected_socket = null;
    selected_object_id = id;
    await Item_clicked();
    normal();
    return models_with_available_joints.filter((m) => m.object_id === id).pop();
  };

  const remove = (model) => {
    picked_mesh = model.mesh;
    Trash_picked_mesh({});
    normal();
  };

  /** Empty the yard. Deleting a tower takes everything resting on it. */
  const reset = async () => {
    let guard = 0;
    while (models_with_available_joints.length && guard++ < 50) {
      remove(models_with_available_joints[0]);
    }
    normal();
  };

  const worldY = (object) => {
    const v = new THREE.Vector3();
    object.getWorldPosition(v);
    return +v.y.toFixed(4);
  };

  /** A tower with a swing beam on it, the rig most tests need. */
  const beamRig = async (towerId, beamId) => {
    await reset();
    const tower = await placeFirst(towerId);
    const beamLayer = beamId.endsWith("-10") ? "b10" : "b8";
    const beam = await place(socketFor(tower, beamLayer), beamId);
    return { tower, beam };
  };

  // ————————————————————————————————————————————————— start

  const welcome = document.querySelectorAll(".welcome-option");
  if (welcome.length) welcome[0].click();
  await idle(600);
  await configsReady;
  await reset();

  const t0 = performance.now();

  // ————————————————————————————————————————————————— sockets

  try {
    suite("sockets");
    const tower = await placeFirst("P-PT");

    check("Play Tower joints", tower.joints.length, 20);
    check("Play Tower sockets", tower.sockets().length, 16);

    const post = tower.sockets().find((s) => s.joints.some((j) => j.layer === "scope"));
    check("a post is one socket offering both toys", post.joints.map((j) => j.layer).sort(), ["scope", "wheel"]);

    // Filling either side of a shared opening closes the whole thing. This is
    // the bug the socket work was written for: the twin used to keep its dot.
    await place(post, "SSC");
    check("filling a post closes it", Socket_is_open(post), false);
    check("both of its joints are taken", post.joints.every((j) => !j.available), true);

    remove(models_with_available_joints.filter((m) => m.object_id === "SSC").pop());
    check("deleting reopens the post", Socket_is_open(post), true);

    // ...and it works whichever of the two goes in first.
    await place(post, "SW");
    check("a wheel closes it the same way", Socket_is_open(post), false);
    remove(models_with_available_joints.filter((m) => m.object_id === "SW").pop());

    const { beam } = await beamRig("P-PT", "P-AB-3-8");
    const shared = beam.sockets().find((s) => s.joints.length > 1);
    check("a beam's last hanger takes a swing or a glider", shared.joints.map((j) => j.layer).sort(), ["s", "sh"]);
    await place(shared, "TZR");
    check("a swing there closes the glider option too", Socket_is_open(shared), false);

    // A part's own spare facing used to draw a dot on top of its own hanger.
    await reset();
    const bs = await probe("BS");
    check("the baby swing's two facings are one socket", bs.model.sockets().length, 1);
    check(
      "...offering both directions",
      bs.model.sockets()[0].joints.map((j) => j.direction).sort(),
      [0, 2]
    );
    bs.done();
  } catch (e) { fail("sockets suite", e); }

  // ————————————————————————————————————————————————— swing fit

  try {
    suite("swing fit");
    for (const [towerId, beamId, variant] of [
      ["P-PT", "P-AB-3-8", "b8"],
      ["P-KT", "P-AB-4-10", "b10"],
    ]) {
      const { beam } = await beamRig(towerId, beamId);
      if (!beam) { fail(`${beamId} placed`, "beam was refused"); continue; }

      for (const swingId of ["BS", "SS", "TZR"]) {
        const socket = socketFor(beam, "s");
        if (!socket) continue;
        const hostY = worldY(socket.joints.find((j) => j.available));
        const swing = await place(socket, swingId);
        if (!swing) { fail(`${swingId} on ${beamId}`, "refused"); continue; }

        const mate = swing.joints.find((j) => j.connected);
        // The swing has to sit exactly on the beam, on the mesh built for that
        // beam length. Getting the layer wrong hangs it 0.61 too low.
        check(`${swingId} on ${beamId} sits on the beam`, worldY(mate) - hostY, 0);
        check(`${swingId} morphs to ${variant}`, swing.layers[swing.meshes.indexOf(swing.mesh)], variant);
      }
    }
  } catch (e) { fail("swing fit suite", e); }

  // ————————————————————————————————————————————————— connection rules

  try {
    suite("rules");

    for (const [plug, host, want] of [
      ["6", "6", true],
      ["6", "8", false],
      ["deck", "6", true],
      ["deck", "8", true],
      ["deck", "s", false],
      ["deck", "picnic", false],
      ["deck", "0", false],
      ["b8", "ds", true],
      ["s", "s", true],
    ]) {
      check(`${plug} -> ${host}`, Layers_connect(plug, host), want);
    }

    // Only a part with a tire mesh variant may take a tire-only hanger. This
    // was enforced in the catalog listing but in none of the placement rules,
    // so any swing could be snapped onto it.
    await reset();
    const summit = await placeFirst("P-ST");
    const tireHanger = summit.joints.find((j) => j.tire_only);
    check("Summit Tower has a tire-only hanger", !!tireHanger, true);

    for (const [id, want] of [["MTS", true], ["SS", false], ["VTS", false], ["BS", false]]) {
      const p = await probe(id);
      check(`${id} on the tire hanger`, !!Find_plug_joint_for(p.model, tireHanger), want);
      p.done();
    }

    // A deck part fits any deck height and nothing else.
    const { beam } = await beamRig("P-PT", "P-AB-3-8");
    const tower = models_with_available_joints.find((m) => m.object_id === "P-PT");
    const hanger = socketFor(beam, "s");
    for (const id of ["TIC", "BUB", "Bridge", "Tunnel"]) {
      const p = await probe(id);
      const deckJoint = tower.joints.find((j) => Is_deck_layer(j.layer) && j.available);
      check(`${id} fits a deck`, !!Find_plug_joint_for(p.model, deckJoint), true);
      check(`${id} refuses a swing hanger`, !!Find_mate_in_socket(p.model, hanger), false);
      p.done();
    }
  } catch (e) { fail("rules suite", e); }

  // ————————————————————————————————————————————————— spanning parts

  try {
    suite("spanning");
    await reset();

    // A bridge fits any deck height, but both its ends must meet the same one.
    const dx = await placeFirst("P-DST");           // carries 5ft and 7ft decks
    const six = dx.joints.find((j) => j.layer === "6" && j.available);
    const eight = dx.joints.find((j) => j.layer === "8" && j.available);

    const loose = await probe("Bridge");
    check("an unattached bridge accepts 5ft", Joints_connect(loose.joint, six), true);
    check("an unattached bridge accepts 7ft", Joints_connect(loose.joint, eight), true);
    loose.done();

    const bridge = await place(dx.sockets().find((s) => s.joints.includes(six)), "Bridge");
    if (bridge) {
      const freeEnd = bridge.joints.find((j) => j.available);
      check("attached to 5ft, it locks to 5ft", Deck_height_locked_to(bridge), "6");
      check("...still accepts another 5ft", Joints_connect(freeEnd, six), true);
      check("...and now refuses 7ft", Joints_connect(freeEnd, eight), false);
    } else {
      fail("bridge placed on a deck", "refused");
    }

    // A bridge has no legs, so it cannot be the first thing in an empty yard.
    await reset();
    const offered = templates().filter((m) => m.capable()).map((m) => m.object_id);
    check("an empty yard offers only towers", offered.sort(), [
      "P-DPT", "P-DSMT", "P-DST", "P-KT", "P-PT", "P-ST", "P-WT",
    ]);
  } catch (e) { fail("spanning suite", e); }

  // ————————————————————————————————————————————————— handle accessories

  try {
    suite("handrails");
    for (const [id, want] of [
      ["HGR", true], ["HR", true],
      ["P-STEP-5", false], ["WS-10", false], ["P-PT", false],
    ]) {
      check(`${id} is a handle accessory`, Is_handle_accessory(template(id)), want);
    }

    await reset();
    const tower = await placeFirst("P-PT");
    const step = await place(socketFor(tower, "6"), "P-STEP-5");
    const a = await place(socketFor(step, "handle"), "HGR");
    const b = await place(socketFor(step, "handle"), "HR");
    check("both rails mount on a step", [!!a, !!b], [true, true]);

    // A step and its handrails share a category, which every other pair is
    // forbidden. The exception has to be scoped to the accessory, or a step
    // could attach to another step's handle socket.
    //
    // Both of the first step's handles are taken by the rails placed above, so
    // this asks about a second step's free one.
    const freeStep = await place(socketFor(tower, "6"), "P-STEP-5");
    const handle = freeStep && freeStep.joints.find((j) => j.layer === "handle" && j.available);
    check("a second step offers a free handle", !!handle, true);
    for (const [id, want] of [["HGR", true], ["WS-10", false], ["P-STEP-5", false], ["SS", false]]) {
      check(`handle socket accepts ${id}`, template(id).capable({ joint: handle }), want);
    }
  } catch (e) { fail("handrails suite", e); }

  // ————————————————————————————————————————————————— deletion

  try {
    suite("deletion");

    const stepRig = async () => {
      await reset();
      const tower = await placeFirst("P-PT");
      const step = await place(socketFor(tower, "6"), "P-STEP-5");
      const a = await place(socketFor(step, "handle"), "HGR");
      const b = await place(socketFor(step, "handle"), "HR");
      return { tower, step, a, b };
    };

    let rig = await stepRig();
    remove(rig.step);
    check("deleting a step takes both its rails", placed(), ["P-PT"]);

    rig = await stepRig();
    remove(rig.tower);
    // The reported bug: rails used to survive their tower, hanging in mid-air.
    check("deleting a tower takes step and rails", placed(), []);

    rig = await stepRig();
    remove(rig.a);
    check("deleting one rail leaves the rest", placed(), ["HR", "P-PT", "P-STEP-5"]);

    const swingRig = async () => {
      const { tower, beam } = await beamRig("P-PT", "P-AB-3-8");
      for (const id of ["SS", "BS"]) await place(socketFor(beam, "s"), id);
      return { tower, beam };
    };

    let sw = await swingRig();
    remove(sw.tower);
    check("deleting a tower takes beam and swings", placed(), []);

    sw = await swingRig();
    remove(sw.beam);
    check("deleting a beam takes its swings, keeps the tower", placed(), ["P-PT"]);

    check("a tower stands on its own", Is_free_standing(template("P-PT")), true);
    check("a bridge does not", Is_free_standing(template("Bridge")), false);
  } catch (e) { fail("deletion suite", e); }

  // ————————————————————————————————————————————————— save and restore

  try {
    suite("save/restore");
    await reset();
    const tower = await placeFirst("P-PT");
    const beam = await place(socketFor(tower, "b8"), "P-AB-3-8");
    await place(socketFor(beam, "s"), "BS");
    await place(socketFor(tower, "scope"), "SSC");

    const snapshot = blueprint.get_snapshot({});
    const links = () =>
      models_with_available_joints
        .map((m) =>
          m.joints
            .filter((j) => j.connected)
            .map((j) => `${m.object_id}.${j.name}->${j.connected.model.object_id}.${j.connected.name}`)
            .sort()
            .join(" | ")
        )
        .sort();

    const original = links();
    const reload = async (state) => {
      await Ensure_models_for_state(state);
      blueprint.restore({ state });
      await idle(400);
      return links();
    };

    check("round trip", await reload(snapshot), original);

    // Names must be what restore actually reads, not merely present. Corrupt
    // every index and the result should be unchanged.
    const corrupted = JSON.parse(snapshot);
    for (const m of corrupted.models_data) {
      for (const c of m.connections || []) { c.my_joint_index = 999; c.connected_to.joint_index = 999; }
      for (const j of m.joints || []) { j.index = 999; j.link.joint_index = 999; }
    }
    check("names beat corrupted indices", await reload(JSON.stringify(corrupted)), original);

    // Designs saved before names existed still have to load.
    const legacy = JSON.parse(snapshot);
    for (const m of legacy.models_data) {
      for (const c of m.connections || []) { delete c.my_joint_name; delete c.connected_to.joint_name; }
      for (const j of m.joints || []) { delete j.name; delete j.link.joint_name; }
    }
    check("index-only saves still load", await reload(JSON.stringify(legacy)), original);
  } catch (e) { fail("save/restore suite", e); }

  // ————————————————————————————————————————————————— catalog

  try {
    suite("catalog");
    for (const file of ["_175 Jolly Retreat.json", "_611 Summit Escape.json", "_111 Family Favorite.json"]) {
      const state = await (await fetch("assets/catalog/" + encodeURIComponent(file))).text();
      await Ensure_models_for_state(state);
      blueprint.restore({ state });
      await idle(500);

      const wanted = JSON.parse(state).models_data.reduce((n, m) => n + (m.connections || []).length, 0);
      const made = models_with_available_joints.reduce((n, m) => n + m.joints.filter((j) => j.connected).length, 0);
      check(`${file.slice(0, 22)} restores every connection`, made, wanted);

      // A joint may legitimately be closed without a connection: the socket
      // rule retires the twin of a filled opening, and a tower's exclusion
      // group retires the positions a climber now overlaps. Anything closed
      // for neither reason has lost track of why.
      const dangling = [];
      for (const m of models_with_available_joints)
        for (const j of m.joints)
          if (!j.available && !j.connected && !j.closed_by_socket && !j.exclusion_layer)
            dangling.push(`${m.object_id}.${j.name}`);
      check(`${file.slice(0, 22)} leaves no joint closed for no reason`, dangling, []);
    }
  } catch (e) { fail("catalog suite", e); }

  // ————————————————————————————————————————————————— railing cut-outs

  try {
    suite("cut-outs");
    await reset();
    const tower = await placeFirst("P-PT");
    const slats = () => {
      let hidden = 0;
      tower.mesh.traverse((m) => {
        if (m.name && m.name.toLowerCase().includes("fence") && !m.visible) hidden++;
      });
      return hidden;
    };

    check("nothing hidden to start", slats(), 0);
    await place(socketFor(tower, "6"), "WS-10");
    const bySlide = slats();
    check("a slide cuts some railing", bySlide > 0, true);

    // Tic-Tac-Toe goes where a slide goes and takes the same opening. Its joint
    // carries no geometry, so it used to cut nothing and sit behind the rails.
    await place(socketFor(tower, "6"), "TIC");
    check("tic-tac-toe cuts as much as the slide", slats() - bySlide, bySlide);
  } catch (e) { fail("cut-outs suite", e); }

  // ————————————————————————————————————————————————— report

  await reset();
  const elapsed = Math.round(performance.now() - t0);
  const failures = results.filter((r) => !r.ok);

  console.table(
    results.map((r) => ({
      suite: r.group,
      check: r.name,
      ok: r.ok ? "pass" : "FAIL",
      actual: Array.isArray(r.actual) ? r.actual.join(",") : r.actual,
      expected: Array.isArray(r.expected) ? r.expected.join(",") : r.expected,
    }))
  );

  const summary = `${results.length - failures.length}/${results.length} passed in ${elapsed}ms`;
  if (failures.length) {
    console.error(`REGRESSION: ${failures.length} failing — ${summary}`);
    for (const f of failures) console.error(`  ${f.group} / ${f.name}`, { actual: f.actual, expected: f.expected });
  } else {
    console.log(`All green — ${summary}`);
  }

  window.__regression = { results, failures, summary };
  return { summary, failures: failures.map((f) => `${f.group} / ${f.name}`) };
})();

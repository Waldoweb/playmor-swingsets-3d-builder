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

  /** What is in the yard, ignoring the toys a tower arrives fitted with. */
  const built = () =>
    models_with_available_joints
      .filter((m) => !["SSC", "SW"].includes(m.object_id))
      .map((m) => m.object_id)
      .sort();

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

  /**
   * Place `id` into `socket`; returns the model, or null if it was refused.
   *
   * Found by id rather than by taking the last thing added: a tower arrives
   * with a scope and a wheel fitted straight after it, so "the last model" is
   * one of the toys. That caught me out and had the spanning checks measuring
   * a steering wheel's position instead of the tower's.
   */
  const place = async (socket, id) => {
    const before = models_with_available_joints.filter((m) => m.object_id === id).length;
    selected_socket = socket;
    selected_object_id = id;
    await Item_clicked();
    normal();
    const mine = models_with_available_joints.filter((m) => m.object_id === id);
    return mine.length > before ? mine[mine.length - 1] : null;
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

    // A Play Tower's post carries its two toy mounts close enough together to
    // be one opening. Both are layer `toy` now — scope, wheel and mailbox were
    // three names for one kind of fitting.
    const post = tower.sockets().find((s) => s.joints.length > 1 && s.joints.every((j) => j.layer === "toy"));
    check("a post is one socket, not two", !!post, true);

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

    // A part's own spare facing must not draw a dot on top of its own hanger.
    await reset();
    const bs = await probe("BS");
    check("the baby swing's two facings are one socket", bs.model.sockets().length, 1);
    check(
      "...offering both directions",
      bs.model.sockets()[0].joints.map((j) => j.direction).sort(),
      [0, 2]
    );
    bs.done();

    // ...and the same asked of a PLACED one, which is a different question.
    // The check above passed while the bug was live: the sockets were right,
    // but the pass that closes them ran before the part joined the list it
    // iterates, so nothing ever looked at them.
    const rig = await beamRig("P-PT", "P-AB-3-8");
    const placedSwing = await place(socketFor(rig.beam, "s"), "BS");
    Tik({});
    check("a placed baby swing closes its unused facing",
      placedSwing.joints.filter((j) => j.available).length, 0);
    check("...and draws no marker of its own",
      browse_sockets.filter((s) => s.model === placedSwing).length, 0);
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

    // The whole point of a bridge is to join two towers, so the second tower
    // has to be offered at its free end — and only towers whose deck is at the
    // height the bridge has already committed to.
    await reset();
    const near = await placeFirst("P-PT");                 // 5 ft decks only
    const span = await place(socketFor(near, "6"), "Bridge");
    const farEnd = span.sockets().find((s) => Socket_is_open(s));
    const at_far_end = templates().filter((m) => m.capable({ socket: farEnd })).map((m) => m.object_id);

    check("a second tower is offered at the bridge's free end", at_far_end.includes("P-WT"), true);
    check("King's Tower is not — it has no 5 ft deck", at_far_end.includes("P-KT"), false);
    check("nor is a 7 ft slide", at_far_end.includes("SWS-14"), false);

    const far = await place(farEnd, "P-WT");
    check("and it attaches", !!far, true);
    check("so the bridge spans two towers",
      span.joints.map((j) => (j.connected ? j.connected.model.object_id : "free")),
      ["P-PT", "P-WT"]);

    // A bridge should meet the middle of a tower's end, not run into its
    // flank. The DX towers are half again as deep as they are wide, so the
    // first joint that happened to fit was a long side and they ended up set
    // back from the span.
    const plan = (m) => {
      const b = new THREE.Box3().setFromObject(m.mesh);
      return { x: (b.min.x + b.max.x) / 2, z: (b.min.z + b.max.z) / 2 };
    };
    for (const id of ["P-WT", "P-DST", "P-DSMT", "P-ST"]) {
      await reset();
      const first = await placeFirst("P-PT");
      const span = await place(socketFor(first, "6"), "Bridge");
      const second = await place(span.sockets().find((s) => Socket_is_open(s)), id);
      check(`${id} squares up with the span`, second ? +(plan(second).z - plan(span).z).toFixed(2) : null, 0);
    }

    await reset();
    const near2 = await placeFirst("P-PT");
    const span2 = await place(socketFor(near2, "6"), "Bridge");
    await place(span2.sockets().find((s) => Socket_is_open(s)), "P-WT");

    // Two towers either side of a span should have their roofs running the same
    // way, not square to each other. Measured on the roof itself rather than on
    // yaw: a roof does not reliably run along its tower's length, and the DX
    // Play Tower's runs across its short way, so equal yaws can still leave two
    // roofs at right angles.
    {
      let joined = 0;
      const square = [];
      for (const firstId of ["P-PT", "P-KT"])
        for (const spanId of ["Bridge", "Tunnel"])
          for (const secondId of ["P-PT", "P-DPT", "P-WT", "P-ST", "P-DST", "P-DSMT", "P-KT"]) {
            await reset();
            const one = await placeFirst(firstId);
            const link = await place(socketFor(one, firstId === "P-KT" ? "8" : "6"), spanId);
            if (!link) continue;
            const two = await place(link.sockets().find((s) => Socket_is_open(s)), secondId);
            if (!two) continue;                       // refused on height, as it should be
            joined++;
            if (Roof_axis(one) !== Roof_axis(two))
              square.push(`${firstId}/${spanId}/${secondId}`);
          }
      check("every joined pair has parallel roofs", square, []);

      // ...and the answer must not depend on which way the yard happens to be
      // turned. It used to: at one quarter turn the collision test rejected
      // every roof-aligned joint, because it measured the part in the pose it
      // had rather than the one it would be turned into, and the fallback was
      // a crooked join.
      const crooked = [];
      for (const turn of [0, 90, 180, 270])
        for (const secondId of ["P-PT", "P-DPT", "P-WT", "P-ST", "P-DST", "P-DSMT"]) {
          await reset();
          const one = await placeFirst("P-PT");
          one.yaw = turn;
          one.mesh.rotation.y = turn * Deg2Rad;
          one.mesh.updateMatrixWorld(true);
          const link = await place(socketFor(one, "6"), "Bridge");
          if (!link) { crooked.push(`${turn}deg/${secondId}: no bridge`); continue; }
          const two = await place(link.sockets().find((s) => Socket_is_open(s)), secondId);
          if (!two) { crooked.push(`${turn}deg/${secondId}: refused`); continue; }
          if (Roof_axis(one) !== Roof_axis(two)) crooked.push(`${turn}deg/${secondId}`);
        }
      check("roofs stay parallel whichever way the yard is turned", crooked, []);
      // A count rather than a threshold, so a rule that quietly starts refusing
      // everything shows up here instead of passing on an empty set. Play Tower
      // reaches the six towers with a 5ft deck, King's the three with a 7ft
      // one, across two kinds of span.
      check("pairs actually joined", joined, 18);
    }

    await reset();
    const near3 = await placeFirst("P-PT");
    const span3 = await place(socketFor(near3, "6"), "Bridge");
    await place(span3.sockets().find((s) => Socket_is_open(s)), "P-WT");

    // Two towers still may not be joined directly — that is what a bridge is for.
    const deck = near3.joints.find((j) => j.layer === "6" && j.available);
    const deckSocket = near3.sockets().find((s) => s.joints.includes(deck));
    check("a tower cannot attach straight to another tower",
      templates().find((m) => m.object_id === "P-DPT").capable({ socket: deckSocket }), false);

    // The same at 7 ft, from the other side.
    await reset();
    const tall = await placeFirst("P-KT");                 // 7 ft decks only
    const span7 = await place(socketFor(tall, "8"), "Bridge");
    const end7 = span7.sockets().find((s) => Socket_is_open(s));
    const offered7 = templates().filter((m) => m.capable({ socket: end7 })).map((m) => m.object_id);
    check("a 7 ft bridge offers only 7 ft towers",
      offered7.filter((id) => templates().find((m) => m.object_id === id).category === 0).sort(),
      ["P-DSMT", "P-DST", "P-KT"]);

    // A bridge has no legs, so it cannot be the first thing in an empty yard.
    await reset();
    const offered = templates().filter((m) => m.capable()).map((m) => m.object_id);
    check("an empty yard offers only towers", offered.sort(), [
      "P-DPT", "P-DSMT", "P-DST", "P-KT", "P-PT", "P-ST", "P-WT",
    ]);
  } catch (e) { fail("spanning suite", e); }

  // ————————————————————————————————————————————————— disabled joints

  try {
    suite("disabled joints");
    // The Summit Tower offered a mailbox mount on each side that the product
    // does not sell. Both were taken out by prefixing the node name, so the app
    // no longer sees them as joints at all.
    await reset();
    const summit = await placeFirst("P-ST");
    const disabled = [];
    summit.mesh.traverse((o) => {
      if (o.name && o.name.startsWith("disabled_")) disabled.push(o.name);
    });
    check("both Summit mailbox mounts are disabled in the model", disabled.length, 2);
    check("...and none of them is a joint any more",
      summit.joints.some((j) => j.name.startsWith("disabled_")), false);

    // Summit keeps its eight post mounts, which now take any toy.
    check("Summit still offers its eight toy points",
      summit.sockets().filter((s) => s.joints.some((j) => j.layer === "toy")).length, 8);

    // The other two towers kept their extra mounts, so they have more.
    for (const [id, points] of [["P-WT", 10], ["P-KT", 4]]) {
      await reset();
      const tower = await placeFirst(id);
      check(`${id} offers ${points} toy points`,
        tower.sockets().filter((s) => s.joints.some((j) => j.layer === "toy")).length, points);
      check(`${id} still takes a mailbox`,
        templates().find((m) => m.object_id === "MAIL").capable(), true);
    }
    await reset();
  } catch (e) { fail("disabled joints suite", e); }

  // ————————————————————————————————————————————————— toy mounts

  try {
    suite("toy mounts");
    const TOYS = ["SW", "SHW", "SSC", "MAIL", "TEL"];
    const refused = [];
    const counts = {};
    for (const id of ["P-PT", "P-DPT", "P-WT", "P-ST", "P-DST", "P-DSMT", "P-KT"]) {
      await reset();
      const tower = await placeFirst(id);
      const points = tower.sockets().filter((s) => s.joints.some((j) => j.layer === "toy"));
      counts[id] = points.length;
      // Two arrive filled, so only the open ones can be asked about.
      const free = points.filter((s) => Socket_is_open(s));
      // Scope, wheel and mailbox were three names for one fitting. Every toy
      // must now go on every toy point, on every tower.
      for (const socket of free)
        for (const toy of TOYS)
          if (!templates().find((m) => m.object_id === toy).capable({ socket }))
            refused.push(`${id}/${toy}`);
    }
    check("every toy fits every toy point", [...new Set(refused)], []);
    check("and the towers offer the expected number of them", counts, {
      "P-PT": 4, "P-DPT": 3, "P-WT": 10, "P-ST": 8, "P-DST": 2, "P-DSMT": 8, "P-KT": 4,
    });

    // All five actually place on one tower.
    await reset();
    const summit = await placeFirst("P-ST");
    // Two are already on, so three more go on.
    let fitted = 2;
    for (const toy of TOYS.filter((t) => !["SSC", "SW"].includes(t))) {
      const socket = summit.sockets().find(
        (s) => Socket_is_open(s) && s.joints.some((j) => j.layer === "toy" && j.available)
      );
      if (!socket) break;
      if (await place(socket, toy)) fitted++;
    }
    check("all five toys are on one tower", fitted, 5);
    await reset();
  } catch (e) { fail("toy mounts suite", e); }

  // ————————————————————————————————————————————————— default fittings

  try {
    suite("fittings");
    const settle = () => idle(250);   // the toys load on demand and arrive just behind

    for (const [id, twoRows] of [
      ["P-WT", true], ["P-ST", true], ["P-DSMT", true], ["P-KT", true],
      ["P-PT", false], ["P-DPT", false], ["P-DST", false],
    ]) {
      await reset();
      await placeFirst(id);
      await settle();
      const fitted = placed().filter((x) => x !== id);

      // A tower comes with the toy for each mount it was drawn with, and no
      // more. King's Tower has had both its scope mounts taken out, so it
      // arrives with the wheel alone. Read off the tower rather than kept as a
      // list here: a mount added or removed in the model changes what this
      // expects, without anyone remembering to edit the test.
      const tower = models_with_available_joints.find((x) => x.object_id === id);
      const wants = modelManifest.default_fittings.filter((f) =>
        tower.joints.some((j) => j.name.includes(f.mount))
      );
      check(`${id} arrives with ${wants.map((f) => f.part).join(" + ") || "no toys"}`,
        fitted, wants.map((f) => f.part).sort());

      // Each toy goes on the mount it was drawn for. They share a layer now,
      // but not a facing: on the DX Play Tower the scope mount on a side points
      // one way and the wheel mount on the same side points the other, so a
      // wheel on a scope mount comes out backwards. Weldon spotted exactly
      // that. The joint names still say which mount is which.
      for (const { part: toy, mount } of wants) {
        const m = models_with_available_joints.find((x) => x.object_id === toy);
        const j = m && m.joints.find((x) => x.connected);
        check(`${id} puts the ${toy} on a ${mount} mount`,
          !!j && j.connected.name.includes(mount), true);
      }

      // Where the tower has two rows the scope goes on the upper one. Where its
      // mounts are all at one height there is no upper, so no claim is made —
      // nor where the tower did not come with both toys to compare.
      if (twoRows && wants.length === 2) {
        const at = (objectId) => {
          const m = models_with_available_joints.find((x) => x.object_id === objectId);
          const j = m && m.joints.find((x) => x.connected);
          const v = new THREE.Vector3();
          if (j) j.getWorldPosition(v);
          return v.y;
        };
        check(`${id} puts the scope above the wheel`, at("SSC") > at("SW"), true);
      }
    }

    // Removable one at a time, and they go with their tower.
    await reset();
    await placeFirst("P-ST");
    await settle();
    remove(models_with_available_joints.find((m) => m.object_id === "SSC"));
    check("deleting the scope leaves the tower and the wheel", placed(), ["P-ST", "SW"]);
    remove(models_with_available_joints.find((m) => m.object_id === "P-ST"));
    check("deleting the tower takes the rest", placed(), []);

    // A saved design says what it contains; nothing is added on top.
    const state = await (await fetch("assets/catalog/_175 Jolly Retreat.json")).text();
    await Ensure_models_for_state(state);
    blueprint.restore({ state });
    await idle(600);
    check("restoring a catalogue set adds no fittings",
      models_with_available_joints.length, JSON.parse(state).models_data.length);
    await reset();
  } catch (e) { fail("fittings suite", e); }

  // ————————————————————————————————————————————————— facing

  try {
    suite("facing");
    // Two towers are modelled a quarter turn from the other five. This used to
    // be worked out by reading the name of the mesh inside the GLB, which stops
    // being true the moment a model is re-exported under a different object
    // name — and fails silently, with the tower simply facing the wrong way.
    for (const [id, degrees] of [
      ["P-PT", 0], ["P-DPT", 0], ["P-WT", 0], ["P-DST", 0], ["P-DSMT", 0],
      ["P-ST", 90], ["P-KT", 90],
    ]) {
      await reset();
      const tower = await placeFirst(id);
      check(`${id} faces ${degrees} degrees`, tower.yaw, degrees);
      check(`${id} mesh matches its yaw`, Math.round(tower.mesh.rotation.y * 180 / Math.PI), degrees);
    }
    await reset();
  } catch (e) { fail("facing suite", e); }

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

    // One click fits both sides: a single rail is not something PlayMor sells.
    await place(socketFor(step, "handle"), "HGR");
    const rails = models_with_available_joints.filter((m) => Is_handle_accessory(m));
    check("one click fits a pair", rails.length, 2);
    check("both of the step's handles are filled",
      step.joints.filter((j) => j.layer === "handle").every((j) => !!j.connected), true);

    // A handrail's joint hangs off the mesh that takes the step's slope, so
    // aligning it before that rotation left it adrift of the step it was
    // supposedly bolted to. Both ends must sit exactly on their socket.
    for (const rail of rails) {
      const mate = rail.joints.find((j) => j.connected);
      const gap = new THREE.Vector3().subVectors(
        (() => { const v = new THREE.Vector3(); mate.getWorldPosition(v); return v; })(),
        (() => { const v = new THREE.Vector3(); mate.connected.getWorldPosition(v); return v; })()
      ).length();
      check(`rail on ${mate.connected.name} sits on its socket`, +gap.toFixed(4), 0);
    }

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
      await place(socketFor(step, "handle"), "HGR");   // fits both sides
      return { tower, step };
    };

    let rig = await stepRig();
    check("a step carries a pair of rails",
      models_with_available_joints.filter((m) => Is_handle_accessory(m)).length, 2);
    remove(rig.step);
    check("deleting a step takes both its rails", built(), ["P-PT"]);

    rig = await stepRig();
    remove(rig.tower);
    // The reported bug: rails used to survive their tower, hanging in mid-air.
    check("deleting a tower takes step and rails", placed(), []);

    // Fitted as a pair, removed as a pair. The twin is not orphaned by the
    // removal — the step still holds it up — so it is named explicitly.
    rig = await stepRig();
    const anyRail = models_with_available_joints.find((m) => Is_handle_accessory(m));
    remove(anyRail);
    check("deleting one rail takes its twin", built(), ["P-PT", "P-STEP-5"]);

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
    check("deleting a beam takes its swings, keeps the tower", built(), ["P-PT"]);

    check("a tower stands on its own", Is_free_standing(template("P-PT")), true);
    check("a bridge does not", Is_free_standing(template("Bridge")), false);
  } catch (e) { fail("deletion suite", e); }

  // ————————————————————————————————————————————————— replacing in place

  try {
    suite("replace");
    await reset();
    const tower = await placeFirst("P-PT");
    const slide = await place(socketFor(tower, "6"), "WS-10");

    // Selecting a placed part offers its opening as if it were empty, so the
    // catalogue lists what else would fit there.
    Offer_replacements(slide);
    check("selecting a part offers its opening", replacing && replacing.model.object_id, "WS-10");

    // Asked the way the catalogue asks it — the opening reads as free only
    // inside this scope, which is what makes the answer the same everywhere.
    const fits = With_opening_free(() =>
      templates().filter((m) => m.capable({ socket: replacing.socket })).map((m) => m.object_id)
    );
    check("the DX wave slide is offered", fits.includes("SWS-10"), true);
    check("so is a climber — everything that fits, as when building fresh", fits.includes("P-RC-5"), true);
    check("a swing is not", fits.includes("SS"), false);

    // The opening is only borrowed for that pass; the part is still attached.
    check("the part is still connected afterwards", !!slide.joints.find((j) => j.connected), true);

    selected_object_id = "SWS-10";
    await Item_clicked();
    const swapped = models_with_available_joints.find((m) => m.object_id === "SWS-10");
    const mate = swapped && swapped.joints.find((j) => j.connected);
    check("the swap happened", built(), ["P-PT", "SWS-10"]);
    check("into the same socket", mate && mate.connected.name, "joint,1,6");
    check("sitting exactly on it", mate ? +new THREE.Vector3().subVectors(
      (() => { const v = new THREE.Vector3(); mate.getWorldPosition(v); return v; })(),
      (() => { const v = new THREE.Vector3(); mate.connected.getWorldPosition(v); return v; })()
    ).length().toFixed(4) : null, 0);
    check("and the selection is cleared", replacing, null);

    // Anything resting on the old part goes with it.
    await reset();
    const t2 = await placeFirst("P-PT");
    const beam = await place(socketFor(t2, "b8"), "P-AB-3-8");
    for (const id of ["SS", "BS"]) await place(socketFor(beam, "s"), id);
    Offer_replacements(beam);
    selected_object_id = "P-AB-4-8";
    await Item_clicked();
    check("swapping a beam takes its swings", built(), ["P-AB-4-8", "P-PT"]);

    // A tower is the ground the design stands on, not a part in an opening.
    await reset();
    const lone = await placeFirst("P-PT");
    Offer_replacements(lone);
    check("a free-standing tower offers no replacement", replacing, null);
  } catch (e) { fail("replace suite", e); }

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

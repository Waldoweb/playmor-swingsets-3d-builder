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
    window.__last_check = `${group} / ${name}`;
    return ok;
  }

  // Published so a run that hangs can be asked how far it got — the results
  // array is closure-local and a stuck run reports nothing at all otherwise.
  const suite = (name) => { group = name; window.__suite = name; };

  const fail = (name, error) =>
    results.push({ group, name, ok: false, actual: String(error), expected: "no error" });

  // ————————————————————————————————————————————————— app helpers

  const idle = (ms) => new Promise((r) => setTimeout(r, ms));

  const normal = () => {
    Mode.mode = Mode.normal;
    // Through the app's own hand-emptying, so a part left in hand by a probe
    // comes out of the scene rather than being dropped on the floor of it.
    if (typeof Drop_carried === "function") Drop_carried();
    else { plug_model = null; plug_joint = null; }
    selected_socket = null;
  };

  /**
   * Every connection points both ways, at a model that is in the yard.
   *
   * The invariant the connection bookkeeping rests on, and the one the rest of
   * this suite never asked directly: it counted connections, so a design that
   * came back with the right number of links wired to the wrong parts passed.
   * Restoring two Play Towers on a bridge did exactly that.
   */
  const brokenLinks = () => {
    const out = [];
    for (const m of models_with_available_joints)
      for (const j of m.joints) {
        if (!j.connected) continue;
        const other = j.connected;
        if (!models_with_available_joints.includes(other.model))
          out.push(`${m.object_id}.${j.name} -> ${other.model.object_id} (not in the yard)`);
        else if (other.connected !== j)
          out.push(`${m.object_id}.${j.name} -> ${other.model.object_id}.${other.name}, which points back at ${
            other.connected ? other.connected.model.object_id + "." + other.connected.name : "nothing"}`);
      }
    return out;
  };

  /** Model meshes in the scene that the yard does not know about. */
  const strayMeshes = () =>
    scene.children.filter((c) => c.model && !picked_meshes.includes(c)).length;

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

    // Which of the two it took. Both fit, so the model cannot say which way
    // round the seat belongs -- the directions are mirror images about the
    // beam -- and it used to take whichever came first, seat facing in. Then
    // a fixed joint, which faced the viewer on one beam and away on the
    // other. Weldon asked for it facing the viewer on either beam, so the
    // manifest records where the seat's front is and the builder turns it.
    const front = modelManifest.products.BS.front_yaw;
    check("the manifest says where a baby swing's front is", typeof front, "number");
    const towardsViewer = (swing) => +Front_at(swing, swing.yaw).dot(home_facing).toFixed(3);
    check("a baby swing on the first beam faces the viewer", towardsViewer(placedSwing), 1);

    // Carrying a second beam has to offer the mount on the other side. It did
    // not: the hover turns the carried mesh to face the nearest opening, and
    // the collision test then turned it again, from the model's recorded yaw
    // rather than from the mesh, and so tested a beam pointing back through
    // the tower. The red marker still worked, because that flow never turns
    // the mesh before asking.
    selected_socket = null;
    selected_object_id = "P-AB-3-8";
    await Item_clicked();
    Tik({});
    const otherMount = rig.tower.joints.find((j) => j.layer === "b8" && j.available);
    check("carrying a second beam offers the mount across the tower",
      !!otherMount && carry_targets.includes(otherMount), true);
    normal();

    // The beam on the other side of the tower stands a half turn round, so
    // the same joint would face the seat away. The other joint is taken.
    const otherBeam = await place(socketFor(rig.tower, "b8"), "P-AB-3-8");
    const otherSwing = otherBeam && (await place(socketFor(otherBeam, "s"), "BS"));
    check("...and on the beam across the tower too", otherSwing ? towardsViewer(otherSwing) : "no swing", 1);
    check("...by hanging from the other facing",
      otherSwing ? (otherSwing.joints.find((j) => j.connected) || {}).direction
        : "no swing",
      (v) => v !== (placedSwing.joints.find((j) => j.connected) || {}).direction);
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
      // A beam mount does NOT fit the disc-swing hanger. This table used to
      // say it did, which was a transcription of the implementation rather
      // than anything the catalog wants: a tower's beam mount carries `b8`,
      // so the hanger at the end of a disc swing beam offered all seven
      // towers alongside the disc swing. The disc swing itself carries `ds`
      // on both joints and connects by plain equality, so nothing was relying
      // on the wider rule.
      ["b8", "ds", false],
      ["b10", "ds", false],
      ["ds", "ds", true],
      ["s", "s", true],
    ]) {
      check(`${plug} -> ${host}`, Layers_connect(plug, host), want);
    }

    // ...and the same thing asked the way a person meets it: click the hanger
    // on the end of a disc swing beam and see what the bar offers.
    await reset();
    const discRig = await beamRig("P-WT", "P-AB-DS-8");
    await idle(250);
    // The beam ships with its swing, which fills the very hanger this is
    // about, so take it off to ask the question of a free one. Conditional
    // rather than assumed: the fitting is skipped when the disc swing's
    // geometry has not arrived yet, and this suite runs early enough that it
    // sometimes has not -- which would otherwise make the test pass or fail on
    // download timing rather than on the rule.
    const preFitted = models_with_available_joints.find((m) => m.object_id === "DS-KR");
    if (preFitted) remove(preFitted);
    const dsSocket = discRig.beam.sockets().find((s) =>
      s.joints.some((j) => j.available && j.layer === "ds")
    );
    check("the disc swing beam has a disc-swing hanger", !!dsSocket, true);
    const atDisc = templates()
      .filter((m) => m.capable({ socket: dsSocket }))
      .map((m) => m.object_id)
      .sort();
    check("only the disc swing fits the disc-swing hanger", atDisc, ["DS-KR"]);

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

    // And the other direction, which used not to be stated at all: the tire
    // swing plugs with `s` like every other swing, so it fitted any hanger on
    // any beam. Weldon says it hangs from the frame under a Summit Tower and
    // nowhere else. The catalog agrees, because the listing asks the same
    // predicate now rather than its own half of the rule.
    check("a tire swing is offered while a Summit Tower stands",
      templates().find((m) => m.object_id === "MTS").capable(), true);

    await reset();
    const rig = await beamRig("P-WT", "P-AB-4-8");
    const swings = ["SS", "TZR", "BS", "VTS", "BB"];
    const hangers = rig.beam.sockets().filter((socket) =>
      socket.joints.some((j) => j.available && ["s", "sh"].includes(j.layer))
    );
    check("the beam has four hangers", hangers.length, 4);

    // The end hanger is the one furthest from the tower it is bolted to, and
    // the only one carrying `sh` — on all six beams the tower mount sits at
    // the far end and that hanger at 0.96.
    const reach = (socket) => {
      const at = new THREE.Vector3();
      socket.joints[0].getWorldPosition(at);
      return at.distanceTo(new THREE.Vector3(0, at.y, 0));
    };
    hangers.sort((a, b) => reach(b) - reach(a));
    const offers = (socket, id) =>
      templates().find((m) => m.object_id === id).capable({ socket });

    check("no hanger on a beam takes a tire swing",
      hangers.filter((h) => offers(h, "MTS")).length, 0);
    check("a tire swing is not offered at all once only a beam is free",
      templates().find((m) => m.object_id === "MTS").capable(), false);

    // The horse glider and the bird's nest are sold for the end position only.
    for (const id of ["HG", "BNS"]) {
      check(`the ${id} goes on the hanger nearest the legs`, offers(hangers[0], id), true);
      check(`...and the ${id} on none of the others`,
        hangers.slice(1).filter((h) => offers(h, id)).length, 0);
    }
    // The ordinary swings are unaffected, on all four.
    check("every plain swing still fits every hanger",
      hangers.filter((h) => swings.every((id) => offers(h, id))).length, 4);

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

    // Weldon: a span reaches any deck, so long as both ends are the same
    // height. 4ft is the third and lives on a different tower, so it takes a
    // second host to ask about.
    const play = await probe("P-DPT");
    const four = play.model.joints.find((j) => j.layer === "5");
    check("an unattached bridge accepts 4ft", Joints_connect(loose.joint, four), true);
    play.done();
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

    // Both towers lost the mailbox mounts at their top corners -- the Sky
    // Tower's pair took it from 10 to 8, and King's Tower is down to the two
    // on its end faces. Each keeps its scope and wheel mounts, which take any
    // of the five toys.
    for (const [id, points] of [["P-WT", 8], ["P-KT", 2]]) {
      await reset();
      const tower = await placeFirst(id);
      check(`${id} offers ${points} toy points`,
        tower.sockets().filter((s) => s.joints.some((j) => j.layer === "toy")).length, points);

      // A tower arrives with two toys on it, and King's has exactly two points
      // left -- so both are taken and nothing else fits until one is freed.
      // Clear them before asking, or this measures the fittings rather than
      // what the mounts accept.
      for (const m of models_with_available_joints.filter((x) => x.object_id !== id)) remove(m);
      check(`${id} still takes a mailbox`,
        templates().find((m) => m.object_id === "MAIL").capable(), true);
    }

    // The King's Tower carries a picket panel on one end already, and offered
    // a Side Rail and a Kitchen Kit on top of it. Both points on that end are
    // gone; the open end keeps its one, so neither part is lost.
    await reset();
    const kings = await placeFirst("P-KT");
    const ground = [];
    for (const socket of kings.sockets()) {
      const joint = socket.joints.find((j) => j.available);
      if (!joint) continue;
      const at = new THREE.Vector3();
      joint.getWorldPosition(at);
      if (at.y < 1.6) ground.push(Math.round(at.z * 100) / 100);
    }
    // The railed end is the negative one; the two at its middle are the floor
    // kit and the picnic table, which mount inside rather than on either end.
    check("the King's railed end offers nothing at ground level",
      ground.filter((z) => z < -0.5).length, 0);
    check("...while its open end still does", ground.filter((z) => z > 0.5).length, 1);
    for (const id of ["SR-KT", "KK"]) {
      check(`a ${id} can still go on the King's Tower`,
        templates().find((m) => m.object_id === id).capable(), true);
    }

    // Weldon: the end rail and the picnic table are different places, and a
    // tower carries both at once. No socket in the catalog accepts both
    // layers, so this checks that placing one does not consume the other --
    // and that the Safety Rail still goes on now that its second plug, which
    // had no host left anywhere, has been taken off it.
    const rail = await place(socketFor(kings, "end_rail"), "SR-KT");
    const table = await place(socketFor(kings, "picnic"), "PT-K");
    check("a tower takes an end rail and a picnic table at once",
      [!!rail, !!table], [true, true]);
    check("...and both are still standing", built(), ["P-KT", "PT-K", "SR-KT"]);
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
      // Take off the toys it arrives with first. On a tower with only two toy
      // points both are filled on arrival, and testing just the open ones
      // would pass this suite by having nothing left to test.
      for (const m of models_with_available_joints.filter((x) => x.object_id !== id)) remove(m);
      const points = tower.sockets().filter((s) => s.joints.some((j) => j.layer === "toy"));
      counts[id] = points.length;
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
      "P-PT": 4, "P-DPT": 3, "P-WT": 8, "P-ST": 8, "P-DST": 2, "P-DSMT": 8, "P-KT": 2,
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

    // A disc swing beam brings its swing. The hanger on its end takes exactly
    // one part in the catalog, so the beam is sold with it on.
    await reset();
    const discRig2 = await beamRig("P-WT", "P-AB-DS-8");
    await settle();
    check("a disc swing beam arrives with the disc swing",
      placed().includes("DS-KR"), true);

    // Exactly one. The disc swing carries `ds` on both its joints, so the one
    // left free after it is hung is a hanger of the same layer -- fit it a
    // second time and the beam grows a chain of them. Attach_plug_to calls the
    // fitting back for whatever it just placed, so this is guarded rather than
    // merely unlikely.
    check("and exactly one of them",
      placed().filter((id) => id === "DS-KR").length, 1);

    const hung = models_with_available_joints.find((m) => m.object_id === "DS-KR");
    check("hung from the beam's disc-swing hanger",
      !!hung.joints.find((j) => j.connected && j.connected.name.includes("disc_swing")), true);

    // Removable, and it does not come back when something else is placed.
    remove(hung);
    check("deleting it takes only the swing",
      placed().sort(), ["P-AB-DS-8", "P-WT", "SSC", "SW"]);
    const spare = discRig2.beam.sockets().find((s) =>
      s.joints.some((j) => j.available && j.layer === "s")
    );
    await place(spare, "SS");
    await settle();
    check("and placing a swing does not refit it",
      placed().filter((id) => id === "DS-KR").length, 0);

    // A plain swing beam has no disc-swing hanger and so brings nothing.
    await reset();
    await beamRig("P-WT", "P-AB-3-8");
    await settle();
    check("a plain swing beam brings nothing of its own",
      placed().sort(), ["P-AB-3-8", "P-WT", "SSC", "SW"]);

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
    // The DX Summit Tower turns the other way, so its roofline runs across
    // the home view rather than end-on (Weldon, 2026-09-08).
    for (const [id, degrees] of [
      ["P-PT", 0], ["P-DPT", 0], ["P-WT", 0], ["P-DST", 0], ["P-DSMT", 270],
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
    check("round trip links all point both ways", brokenLinks(), []);

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
    // Every shipped set, not a sample. These are the designs a customer opens
    // and the client signs off on, and they are the one thing in the build that
    // records what the catalog looked like before any of this work — a saved
    // set binds its connections by joint index, so disabling a joint in a model
    // is exactly the kind of edit that could quietly rearrange one.
    const catalogue = [
      "_111 Family Favorite.json", "_171 Lovely Retreat.json", "_173 Family Joy.json",
      "_175 Jolly Retreat.json", "_211 Scenic Pointe.json", "_223 Friendly Retreat.json",
      "_475 Golden Retreat.json", "_518 Dizzy Delight.json", "_549 Backyard Retreat.json",
      "_611 Summit Escape.json",
    ];
    let drift = 0;
    let worstSet = "";
    const missing = [];
    for (const file of catalogue) {
      const state = await (await fetch("assets/catalog/" + encodeURIComponent(file))).text();
      await Ensure_models_for_state(state);
      blueprint.restore({ state });
      await idle(500);

      // Every connection the file records, less any that contradict each
      // other. Three of the old sets say, from one side, that a scope sits on
      // a deck rail and, from the other, that the same scope sits on a toy
      // mount; restore keeps the first and refuses the second, so those two
      // records yield one joint fewer than their count. A joint named with two
      // different partners is a conflict, and neither of its records is owed.
      const records = [];
      for (const m of JSON.parse(state).models_data)
        for (const c of m.connections || [])
          records.push({
            a: `${m.save_index}.${c.my_joint_name}`,
            b: `${c.connected_to.model_save_index}.${c.connected_to.joint_name}`,
          });
      const partner = new Map();
      const conflicted = new Set();
      for (const r of records)
        for (const [x, y] of [[r.a, r.b], [r.b, r.a]]) {
          if (partner.has(x) && partner.get(x) !== y) conflicted.add(x);
          else partner.set(x, y);
        }
      const consistent = records.filter((r) => !conflicted.has(r.a) && !conflicted.has(r.b)).length;
      const made = models_with_available_joints.reduce((n, m) => n + m.joints.filter((j) => j.connected).length, 0);
      check(`${file.slice(0, 22)} restores every consistent connection (${consistent} of ${records.length})`,
        made >= consistent && made <= records.length, true);

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
      check(`${file.slice(0, 22)} links all point both ways`, brokenLinks(), []);

      // Where every part ended up, against where the file says it was. Pair
      // each saved model with its NEAREST live twin of the same product, never
      // the first one found: a beam carries several identical sling swings, and
      // matching them in list order reports a whole hanger's spacing of drift
      // that is not there.
      const pool = models_with_available_joints.slice();
      for (const saved of JSON.parse(state).models_data) {
        let pick = -1;
        let nearest = Infinity;
        pool.forEach((live, i) => {
          if (live.object_id !== saved.object_id) return;
          const gap = Math.hypot(
            live.mesh.position.x - saved.position.x,
            live.mesh.position.y - saved.position.y,
            live.mesh.position.z - saved.position.z
          );
          if (gap < nearest) { nearest = gap; pick = i; }
        });
        if (pick < 0) { missing.push(`${file}: ${saved.object_id}`); continue; }
        pool.splice(pick, 1);
        if (nearest > drift) { drift = nearest; worstSet = `${file} ${saved.object_id}`; }
      }
    }
    check("every catalogue set restores every part", missing, []);
    // Exact, not approximate: these are the same numbers written back out.
    check(`no part drifts on restore (worst: ${worstSet || "none"})`, drift < 1e-6, true);
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

  // ————————————————————————————————————————————————— layer vocabulary

  try {
    suite("layer vocabulary");
    const products = {};
    for (const [id, product] of Object.entries(modelManifest.products))
      for (const file of product.files || [])
        for (const name of file.joints || []) {
          const layer = name.split(",")[2];
          (products[layer] = products[layer] || new Set()).add(id);
        }

    // The wildcard matched every socket there is, which let a Bridge hang off
    // a swing hanger. It is gone from the models and from Layers_connect, and
    // build_models.js now refuses to build one — this is the same invariant
    // asked from the other end, where a person would actually see it.
    check("no joint is on the wildcard layer", "*" in products, false);

    // A layer only one product knows cannot connect to anything: a model's
    // own joints are never offered to each other, so it takes two. Layer '0'
    // became exactly that the moment the King's Tower railed end came out —
    // the Safety Rail was left holding a plug with nowhere to go. Asking it of
    // the whole catalog finds the next one without anyone having to notice.
    const lonely = Object.entries(products)
      .filter(([, ids]) => ids.size < 2)
      .map(([layer, ids]) => `${layer} (only ${[...ids]})`);
    check("every layer is known to at least two products", lonely, []);
  } catch (e) { fail("layer vocabulary suite", e); }

  // ————————————————————————————————————————————————— marker visibility

  try {
    suite("marker visibility");
    // A tower fence is separate boards, 0.089 wide on a 0.156 pitch, so the
    // gaps run to 0.095. A single ray aimed at a marker on the far rail threads
    // one cleanly and calls the marker visible, which is how the dots from the
    // back of a tower came to show through the front fence. The test is a
    // bundle of five parallel rays now, offset by more than half that gap.
    await reset();
    const tower = await placeFirst("P-KT");

    // Asked of the visibility test directly rather than counted off the drawn
    // markers. browse_sockets is filled by the render loop, and a browser that
    // has put the tab in the background stops calling it — which failed this
    // suite three times over while the thing it tests was working perfectly.
    // Driving the test itself also removes the wait for the 10Hz tick.
    const world = new THREE.Vector3();
    const look = (height, z) => {
      camera.position.set(0.2, height, z);
      camera.lookAt(0, 2.2, 0);
      camera.updateMatrixWorld();
      Refresh_occluder_boxes();
    };
    /** Markers a person would see, on the model's own open sockets. */
    const visible = (model, low, high) => {
      const out = [];
      for (const socket of model.sockets()) {
        const joint = socket.joints.find((j) => j.available);
        if (!joint) continue;
        joint.updateMatrixWorld();
        world.setFromMatrixPosition(joint.matrixWorld);
        if (socket.offset) world.add(socket.offset);
        if (low !== undefined && (world.y <= low || world.y >= high)) continue;
        if (Marker_is_hidden(joint, world, null)) continue;
        out.push(world.z);
      }
      return out;
    };
    // Bounded above as well as below: the swing-beam seat rides at 3.2, clear
    // of the fence with nothing in front of it, and is genuinely visible from
    // either side — hiding that one would be wrong, so it is not what this
    // measures.
    const rails = () => {
      const near = Math.sign(camera.position.z);
      let onNear = 0, onFar = 0;
      for (const z of visible(tower, 2.0, 3.0)) {
        if (Math.sign(z) === near) onNear++; else onFar++;
      }
      return { onNear, onFar };
    };

    look(3.2, 5.2);
    const front = rails();
    check("no far-rail marker draws through the fence", front.onFar, 0);
    check("the near rail still shows its markers", front.onNear > 0, true);

    // Orbiting to the other side has to swap which rail is hidden, or this is
    // a fixed rule about the model rather than an answer about the view.
    look(3.2, -5.2);
    const behind = rails();
    check("the same holds from the other side", behind.onFar, 0);
    check("and the rail now in front shows its markers", behind.onNear > 0, true);

    // Looking down over the fence is the angle that beat the first attempt:
    // the sight line clears the near rail, so a bundle sized to the slat gaps
    // finds nothing in the way and every dot on the back rail draws.
    look(4.4, 4.6);
    check("nor from above, looking down over the rail", rails().onFar, 0);

    // A swing beam is open air. Its hangers sit on the far half of it from
    // half the angles anyone looks from, and a rule that hid the far half on
    // position alone would cull them — which is what happened the last time
    // one was tried. They block no rays, so they survive.
    await reset();
    const host = await placeFirst("P-WT");
    const seat = host.sockets().find((socket) =>
      socket.joints.some((j) => j.available && (j.layer === "b8" || j.layer === "b10"))
    );
    const beam = await place(seat, "P-AB-3-8");
    check("the beam went on", !!beam, true);
    // Stand off the beam's flank, where its hangers are plainly in view.
    camera.position.set(7, 3.4, -2.8);
    camera.lookAt(0, 2.5, -2.8);
    camera.updateMatrixWorld();
    Refresh_occluder_boxes();
    check("a beam's hangers all stay visible from its flank",
      visible(beam).length, 3);

    // The Summit Tower's tire hanger is authored flush under the deck, and the
    // deck is a solid square at exactly that height, so its dot could not be
    // seen from anywhere: 0 of 25 camera positions. Its marker drops a metre to
    // where the tire hangs. Only the dot moves — the swing still attaches to
    // the bracket, which is what marker_offsets is for.
    await reset();
    const summitTower = await placeFirst("P-ST");
    const tireSocket = summitTower.sockets().find((socket) =>
      socket.joints.some((j) => j.tire_only)
    );
    check("the tire hanger's dot is drawn a metre below the bracket",
      tireSocket.offset ? Math.round(tireSocket.offset.y * 100) / 100 : 0, -1);

    const bracket = new THREE.Vector3();
    tireSocket.joints[0].getWorldPosition(bracket);
    check("the bracket itself has not moved", Math.round(bracket.y * 100) / 100, 1.5);

    // Seen from eye level and from above, both of which used to show nothing.
    let seen = 0;
    for (const height of [1.6, 2.2, 3.0]) {
      camera.position.set(0.1, height, 6);
      camera.lookAt(0, 1.6, 0);
      camera.updateMatrixWorld();
      Refresh_occluder_boxes();
      const at = bracket.clone().add(tireSocket.offset);
      if (!Marker_is_hidden(tireSocket.joints[0], at, null)) seen++;
    }
    check("and it can be seen from eye level and above", seen, 3);

    // The swing still lands on the bracket, not on the dot.
    const swing = await place(tireSocket, "MTS");
    check("a tire swing still goes on", !!swing, true);
    const hung = swing && swing.joints.find((j) => j.connected);
    const where = new THREE.Vector3();
    if (hung) hung.getWorldPosition(where);
    check("...at the bracket's own height", Math.round(where.y * 100) / 100, 1.5);
    await reset();

    await reset();
  } catch (e) { fail("marker visibility suite", e); }

  // ————————————————————————————————————————————————— authored heights

  try {
    suite("heights");

    // The disc swing's rope length is geometry inside its own GLB, not
    // anything the app works out, so a rebuild that lost the change would put
    // the seat back at shoulder height with nothing else complaining. It hung
    // at 45 inches while every other seat on a beam sat between 14 and 31;
    // Weldon put it level with the tire and ball swings.
    await reset();
    await beamRig("P-WT", "P-AB-DS-8");
    await idle(250);
    const disc = models_with_available_joints.find((m) => m.object_id === "DS-KR");
    check("the disc swing is fitted", !!disc, true);
    const seat = new THREE.Box3().setFromObject(disc.mesh).min.y * 39.3701;
    check("its seat hangs about 20 inches up", seat > 17 && seat < 24, true);

    // Where a swing beam's dot is drawn, and where the beam actually bolts on,
    // are two different heights on three of the towers. Both are asserted
    // together on purpose: raising the attachment instead of the marker would
    // leave the beam's own A-frame leg hanging in the air, since the leg is
    // baked a fixed distance below the joint.
    for (const [id, name, attach, dot] of [
      ["P-WT", "joint_beam_front,0,b8,3,1", 2.56, 2.93],
      ["P-WT", "joint_beam_back,2,b8,8,6", 2.56, 2.93],
      ["P-KT", "joint_beam_left,3,b10,10,8", 3.2, 3.55],
      ["P-KT", "joint_beam_right,1,b10,5,3", 3.2, 3.55],
      ["P-DST", "joint_beam_front,0,b8,3,1", 2.56, 2.93],
      // ...and the ones that already sat right are untouched. P-DST carries
      // one of each, which is the whole point of keying this by joint name:
      // its 7ft side must not move with its 5ft one.
      ["P-DST", "joint_beam_back,2,b10,10,8", 3.2, 3.2],
      ["P-PT", "joint_beam_front,0,b8,6,2", 2.56, 2.56],
      ["P-DPT", "joint_beam,2,b8,3,2", 2.56, 2.56],
    ]) {
      await reset();
      const tower = await placeFirst(id);
      const joint = tower.joints.find((j) => j.name === name);
      const socket = tower.sockets().find((s) => s.joints.includes(joint));
      const at = new THREE.Vector3();
      joint.getWorldPosition(at);
      const short = `${id} ${name.split(",")[0]}`;
      check(`${short} bolts on at ${attach}`, +at.y.toFixed(2), attach);
      check(`${short} draws its dot at ${dot}`,
        +(at.y + (socket.offset ? socket.offset.y : 0)).toFixed(2), dot);
    }
    await reset();
  } catch (e) { fail("heights suite", e); }

  // ————————————————————————————————————————————————— state hygiene

  try {
    suite("integrity");
    const templateCount = Model.instances.length;

    // Two of one product across a bridge. Restore used to find the far model
    // by product id, so both bridge ends came back on the same tower and the
    // other tower pointed at a joint that no longer pointed back.
    await reset();
    const near = await placeFirst("P-PT");
    const span = await place(socketFor(near, "6"), "Bridge");
    await place(span.sockets().find((s) => Socket_is_open(s)), "P-PT");
    check("two Play Towers on a bridge, before saving", brokenLinks(), []);
    const twins = blueprint.get_snapshot({});
    await Ensure_models_for_state(twins);
    blueprint.restore({ state: twins });
    await idle(300);
    check("...and after restoring", brokenLinks(), []);
    check("both ends of the bridge are on different towers",
      new Set(models_with_available_joints.find((m) => m.object_id === "Bridge").joints
        .map((j) => j.connected && j.connected.model)).size, 2);

    // Nothing lingers from before a reset: not the meshes, not the selection.
    const tower = models_with_available_joints.find((m) => m.object_id === "P-PT");
    selected_socket = socketFor(tower, "6");
    Refresh();
    check("reset clears the chosen spot", selected_socket, null);
    check("reset takes the old meshes out of the scene", strayMeshes(), 0);
    const fresh = await placeFirst("P-PT");
    check("a tower placed after a reset is attached to nothing",
      fresh.joints.filter((j) => j.connected && j.connected.model.object_id === "P-PT").length, 0);
    check("...and every link in the yard is sound", brokenLinks(), []);

    // Same for undo, which rebuilds every model from the snapshot.
    selected_socket = socketFor(fresh, "6");
    Offer_replacements(models_with_available_joints.find((m) => m.object_id === "SW") || null);
    blueprint.undo();
    await idle(100);
    check("undo clears the chosen spot", selected_socket, null);
    check("undo clears the part being swapped", replacing, null);
    check("undo leaves no stray meshes", strayMeshes(), 0);

    // Placing does not register copies as templates.
    check("placed parts are not added to the template list", Model.instances.length, templateCount);

    // Esc is "never mind" for a selected part too.
    await reset();
    const t = await placeFirst("P-WT");
    await idle(250);
    const wheel = models_with_available_joints.find((m) => m.object_id === "SW");
    picked_mesh = wheel.mesh;
    Offer_replacements(wheel);
    check("selecting the wheel offers its opening", replacing && replacing.model.object_id, "SW");
    Keys.code = Keys.esc; Key_up();
    check("Esc drops the swap", replacing, null);
    await place(null, "MAIL");
    check("...so the next tile does not replace the wheel",
      models_with_available_joints.some((m) => m.object_id === "SW"), true);
    normal();
    // And deleting the selected part drops it as well.
    picked_mesh = wheel.mesh; Offer_replacements(wheel);
    remove(wheel);
    check("deleting the selected part drops the swap", replacing, null);

    // Esc while carrying takes the carried mesh out of the scene.
    await reset();
    await placeFirst("P-PT");
    selected_socket = null; selected_object_id = "WS-10";
    await Item_clicked();                              // no spot chosen: goes into the hand
    check("a part with no spot chosen is carried", Mode.mode === Mode.plugging && !!plug_model, true);
    Keys.code = Keys.esc; Key_up();
    check("Esc puts it down and out of the scene", [plug_model, strayMeshes()], [null, 0]);

    // Swapping a swing at the end hanger offers what hangs from the other
    // joint of that opening too.
    const rig = await beamRig("P-WT", "P-AB-3-8");
    const endHanger = rig.beam.sockets().find((s) => s.joints.some((j) => j.layer === "sh"));
    const sling = await place(endHanger, "SS");
    Offer_replacements(sling);
    const swaps = With_opening_free(() =>
      templates().filter((m) => m.capable({ socket: replacing.socket })).map((m) => m.object_id));
    check("a swing on the end hanger can be swapped for the glider and the nest",
      ["HG", "BNS"].every((id) => swaps.includes(id)), true);
    replacing = null;

    // A double-click on a tile is one placement, not one and a copy in hand.
    await reset();
    await template("P-KT").ensure_loaded();
    selected_socket = null; selected_object_id = "P-KT";
    await Promise.all([Item_clicked(), Item_clicked()]);
    check("a double-click places once", placed().filter((id) => id === "P-KT").length, 1);
    check("...with nothing left in hand", plug_model, null);
    normal();

    // A copy of a multi-layer part has one mesh's joints, on a mesh it owns.
    const ss = await probe("SS");
    check("a fresh sling swing has one joint, not one per layer", ss.model.joints.length, 1);
    check("...on a mesh that is one of its layers", ss.model.meshes.includes(ss.model.mesh), true);
    check("...and knows which layer that is", ss.model.layers.includes(ss.model.layer), true);
    ss.done();

    await reset();
    check("an empty yard has an empty scene", strayMeshes(), 0);
  } catch (e) { fail("integrity suite", e); }

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

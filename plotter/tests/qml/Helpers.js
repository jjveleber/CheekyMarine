.pragma library

// Shared by the QML tests: item lookup, the 12 mm control check, the three panel sizes and box maths.

// Every item under `root` (depth first) for which pred holds.
function findAll(root, pred) {
    let out = []
    const stack = [root]
    while (stack.length > 0) {
        const it = stack.pop()
        if (pred(it)) out.push(it)
        for (let i = 0; i < it.children.length; ++i) stack.push(it.children[i])
    }
    return out
}

function byName(root, name) {
    const l = findAll(root, it => it.objectName === name)
    return l.length > 0 ? l[0] : null
}

// Every BigButton under `root` is at least 12 mm both ways (checked through the test case `tc`);
// returns how many there are.
function checkBigButtons(tc, units, root) {
    const buttons = findAll(root, it => it.isBigButton === true)
    tc.verify(buttons.length > 0, "no BigButton found")
    const min = units.mm(12) - 0.5
    for (const b of buttons) {
        tc.verify(b.width >= min && b.height >= min,
                  "BigButton '" + b.text + "' (" + b.objectName + ") is " + b.width + "x" + b.height + ", min " + min)
    }
    return buttons.length
}

function sizes() {
    return [{ tag: "1024x600", w: 1024, h: 600, ppm: 4.626, diagIn: 10.1 },
            { tag: "1280x800", w: 1280, h: 800, ppm: 5.884, diagIn: 10.1 },
            { tag: "1920x1280", w: 1920, h: 1280, ppm: 6.988, diagIn: 13 }]
}

// The item's box in `ref` coordinates.
function box(it, ref) {
    const p = it.mapToItem(ref, 0, 0)
    return { x: p.x, y: p.y, w: it.width, h: it.height }
}

function overlaps(a, b, ref) {
    const p = box(a, ref), q = box(b, ref)
    return p.x < q.x + q.w && q.x < p.x + p.w && p.y < q.y + q.h && q.y < p.y + p.h
}

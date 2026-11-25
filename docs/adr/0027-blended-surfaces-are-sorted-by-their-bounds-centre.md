# Blended surfaces are sorted by their bounds' centre

Unity draws transparent renderers back to front by the distance to the centre of each renderer's bounds, and draws the triangles of one renderer in mesh order. KK's foliage is `Particles/Alpha Blended`, which writes no depth, so that order decides what overlapping trees look like. EEVEE sorts blended objects by their origins instead, and many of a Map's objects have their origin at the Map's centre, far from what they draw. On ground the gate's trees came out in front of the trees behind them, or behind: in the look check one tile of a view was 31 % too bright.

So a renderer that draws a blended material draws through a child object placed at the centre of its bounds, with a copy of its mesh moved by that centre (one copy per mesh). The centre of a box's bounds moves with the box, so the child stands exactly where Unity's renderer bounds have their centre. The node's own object keeps its transform and becomes an empty.

## Considered Options

- **Moving the node objects' origins (rejected)**: no extra objects, but a Placement root's origin is where a user's asset stands, and a parent's origin is what its children are placed from.
- **A sorting child (chosen)**: every node keeps its transform; only drawing moves.

## Consequences

- EEVEE sorts by depth along the view and Unity by distance from the camera; they differ only for renderers far off to the side and close together.
- A renderer's passes and opaque draws move into the child too, so a renderer has one sort key, as in Unity.
- In the look check ground's day eye-0 view's worst tile went from 31 % to 6 %, and 9 of ground's 15 views pass instead of 8.

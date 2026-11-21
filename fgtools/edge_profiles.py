"""Measure straight stroke runs between two outline segments in a compiled glyph."""
import math

from fontTools.misc.bezierTools import segmentSegmentIntersections
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib.path import parse_path


def _segments(drawing):
    for op, pts in drawing.value:
        if op == 'moveTo':
            start = current = pts[0]
        elif op in ('lineTo', 'qCurveTo', 'curveTo'):
            yield [current, *pts]
            current = pts[-1]
        elif op == 'closePath' and current != start:
            yield [current, start]


def _section(point, normal, reach, drawing, edges):
    inside = PointInsidePen(None, point)
    drawing.replay(inside)
    if not inside.getResult():
        return {'status': 'outside-ink'}
    nx, ny = normal
    x, y = point
    cut = [(x - reach * nx, y - reach * ny), (x + reach * nx, y + reach * ny)]
    hits = []
    for index, edge in enumerate(edges):
        for hit in segmentSegmentIntersections(edge, cut):
            # FontTools can also return the intersection of line extensions.
            if 0 <= hit.t1 <= 1 and 0 <= hit.t2 <= 1:
                hits.append((hit.t2, index, hit.t1, hit.pt))
    hits.sort()
    left = [hit for hit in hits if hit[0] < 0.5]
    right = [hit for hit in hits if hit[0] >= 0.5]
    if not left or not right:
        return {'status': 'unbounded'}
    ends = (left[-1], right[0])
    ids = [hit[1] for hit in ends]
    result = {'edges': ids, 'contacts': [hit[3] for hit in ends]}
    for _, index, t, _ in ends:
        edge = edges[index]
        if t < 1e-6 or t > 1 - 1e-6:
            return dict(result, status='corner')
        if len(edge) != 2:
            return dict(result, status='curved-edge')
        dx, dy = edge[1][0] - edge[0][0], edge[1][1] - edge[0][1]
        # A straight track may tolerate an optical taper. Discard oblique cuts.
        if abs(dx * nx + dy * ny) > math.sin(math.radians(10)) * math.hypot(dx, dy):
            return dict(result, status='oblique-contact')
    return dict(result, status='paired', width=math.dist(*result['contacts']))


def edge_profile(commands, start, end, units):
    """Follow a seeded pair along a straight track. Close it at the first missing contact."""
    if not all(math.isfinite(v) for v in (*start, *end)):
        raise ValueError('Edge track coordinates must be finite')
    length = math.dist(start, end)
    if not 0 < length <= 16 * units:
        raise ValueError('Edge track length must be positive and at most 16 em')
    tx, ty = ((b - a) / length for a, b in zip(start, end))
    drawing = RecordingPen()
    parse_path(commands, drawing)
    edges = list(_segments(drawing))
    reach = 1 + max((math.dist(p, start) for edge in edges for p in edge), default=0) + length
    count = max(2, math.ceil(length / (units / 64)))
    readings = []
    pair = None
    for i in range(count + 1):
        point = [a + (b - a) * i / count for a, b in zip(start, end)]
        section = _section(point, (-ty, tx), reach, drawing, edges)
        if pair is not None and section.get('edges') != pair and section['status'] == 'paired':
            section['status'] = 'edge-pair-ended'
            del section['width']
        readings.append(dict(section, point=point))
        if section['status'] != 'paired':
            break
        pair = section['edges']
    widths = [row['width'] for row in readings if row['status'] == 'paired']
    return {'start': start, 'end': end, 'paired_count': len(widths),
            'width_range': [min(widths), max(widths)] if widths else None,
            'stop_reason': None if readings[-1]['status'] == 'paired' else readings[-1]['status'],
            'samples': readings}

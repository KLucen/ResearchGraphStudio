import {
  graphNodeKind,
  type GraphNode,
  type GraphPosition,
} from "./graphTypes";

type LabelBox = { x: number; y: number; width: number; height: number };

export const knowledgeNodeSize = (node: GraphNode) =>
  graphNodeKind(node) === "PAPER" ? 28 : 20;

export function knowledgeNodeText(node: GraphNode, language: string) {
  const zh = node.label_zh?.trim() ?? "";
  const en = node.label_en?.trim() ?? "";
  return {
    primary: language === "en" ? en || zh : zh || en,
    secondary: language === "both" && zh && en && zh !== en ? en : "",
  };
}

function labelWidth(text: string): number {
  // Reserve enough space for the supported scripts while bounding long titles.
  // The spans ellipsize within this box regardless of the system font.
  let width = 12;
  for (const character of text) {
    width += character.charCodeAt(0) > 127 ? 13 : 8;
    if (width >= 136) return 136;
  }
  return width;
}

function intersects(left: LabelBox, right: LabelBox): boolean {
  const gap = 3;
  return (
    left.x < right.x + right.width + gap &&
    right.x < left.x + left.width + gap &&
    left.y < right.y + right.height + gap &&
    right.y < left.y + left.height + gap
  );
}

export function placeKnowledgeLabels(
  nodes: GraphNode[],
  positions: Map<string, GraphPosition>,
  language: string,
  hover: string,
  selected: string,
  compact: boolean,
) {
  const circles = nodes.map((node) => {
    const position = positions.get(node.id);
    const size = knowledgeNodeSize(node);
    const priority =
      node.id === hover
        ? 3
        : node.id === selected
          ? 2
          : graphNodeKind(node) === "PAPER"
            ? 1
            : 0;
    return {
      node,
      x: position?.x ?? 0,
      y: position?.y ?? 0,
      width: size,
      height: size,
      priority,
    };
  });
  const occupied: LabelBox[] = [];
  const labels = new Map<string, LabelBox>();
  for (const circle of [...circles].sort(
    (left, right) => right.priority - left.priority,
  )) {
    if (compact && circle.priority === 0) continue;
    const { node, x, y, width: diameter } = circle;
    const { primary, secondary } = knowledgeNodeText(node, language);
    if (!primary) continue;
    const width = Math.max(labelWidth(primary), labelWidth(secondary));
    const height = secondary ? 32 : 16;
    const horizontal = x + (diameter - width) / 2;
    const vertical = y + (diameter - height) / 2;
    const gap = 6;
    const alternatives = [
      { x: horizontal, y: y + diameter + gap },
      { x: horizontal, y: y - height - gap },
      { x: x + diameter + gap, y: vertical },
      { x: x - width - gap, y: vertical },
    ];
    for (const alternative of alternatives) {
      const box = { ...alternative, width, height };
      if (
        occupied.some((other) => intersects(box, other)) ||
        circles.some((other) => intersects(box, other))
      )
        continue;
      occupied.push(box);
      labels.set(node.id, { ...box, x: box.x - x, y: box.y - y });
      break;
    }
  }
  return labels;
}

function isPathPrefix(leftPath, rightPath) {
  const left = Array.isArray(leftPath) ? leftPath : [];
  const right = Array.isArray(rightPath) ? rightPath : [];
  if (left.length > right.length) {
    return false;
  }
  return left.every((part, index) => part === right[index]);
}

function collectClauseAndDescendants(catalog, clauseId, allowedClauseIds = null) {
  const normalizedClauseId = String(clauseId || "").trim();
  if (!normalizedClauseId) {
    return [];
  }
  const allowed = allowedClauseIds instanceof Set ? allowedClauseIds : null;
  const collected = !allowed || allowed.has(normalizedClauseId) ? [normalizedClauseId] : [];
  const children = catalog?.childrenByParent?.[normalizedClauseId] || [];
  children.forEach((childId) => {
    collected.push(...collectClauseAndDescendants(catalog, childId, allowed));
  });
  return collected;
}

function markNodeAsLoaded(node) {
  return {
    ...node,
    descendantsLoaded: true,
    children: (node.children || []).map((child) => markNodeAsLoaded(child)),
  };
}

function areAllDescendantsSelected(node, selectedSet) {
  return (node.children || []).every((child) => (
    selectedSet.has(String(child?.clauseId || "").trim()) && areAllDescendantsSelected(child, selectedSet)
  ));
}

function mergeNodeTrees(existingNode, incomingNode) {
  if (!existingNode) {
    return incomingNode;
  }
  if (!incomingNode) {
    return existingNode;
  }
  if (existingNode.key !== incomingNode.key) {
    return existingNode;
  }
  if (existingNode.descendantsLoaded && !incomingNode.descendantsLoaded) {
    return existingNode;
  }

  const existingChildren = new Map((existingNode.children || []).map((child) => [child.key, child]));
  const mergedChildren = [];
  (incomingNode.children || []).forEach((incomingChild) => {
    const existingChild = existingChildren.get(incomingChild.key) || null;
    mergedChildren.push(mergeNodeTrees(existingChild, incomingChild));
    existingChildren.delete(incomingChild.key);
  });
  existingChildren.forEach((child) => {
    mergedChildren.push(child);
  });

  return {
    ...existingNode,
    ...incomingNode,
    text: existingNode.text || incomingNode.text,
    blocks: Array.isArray(existingNode.blocks) && existingNode.blocks.length ? existingNode.blocks : incomingNode.blocks,
    descendantsLoaded: Boolean(existingNode.descendantsLoaded || incomingNode.descendantsLoaded),
    children: mergedChildren,
  };
}

export function normalizePickerSelectedClauseIdsBySpec(value) {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.entries(value).reduce((accumulator, [specNo, clauseIds]) => {
    const normalizedSpecNo = String(specNo || "").trim();
    if (!normalizedSpecNo) {
      return accumulator;
    }
    const normalizedClauseIds = [...new Set((Array.isArray(clauseIds) ? clauseIds : []).map((item) => String(item || "").trim()).filter(Boolean))];
    if (!normalizedClauseIds.length) {
      return accumulator;
    }
    return {
      ...accumulator,
      [normalizedSpecNo]: normalizedClauseIds,
    };
  }, {});
}

export function getPickerSelectedClauseIds(selectedClauseIdsBySpec, specNo) {
  const normalizedSpecNo = String(specNo || "").trim();
  if (!normalizedSpecNo) {
    return [];
  }
  return [...(normalizePickerSelectedClauseIdsBySpec(selectedClauseIdsBySpec)[normalizedSpecNo] || [])];
}

export function togglePickerClauseSelection(
  selectedClauseIdsBySpec,
  specNo,
  clauseId,
  checked,
  catalog = null,
  allowedClauseIds = null
) {
  const normalized = normalizePickerSelectedClauseIdsBySpec(selectedClauseIdsBySpec);
  const normalizedSpecNo = String(specNo || "").trim();
  const normalizedClauseId = String(clauseId || "").trim();
  if (!normalizedSpecNo || !normalizedClauseId) {
    return normalized;
  }
  const current = new Set(normalized[normalizedSpecNo] || []);
  const clauseIdsToApply = collectClauseAndDescendants(catalog, normalizedClauseId, allowedClauseIds);
  if (checked) {
    clauseIdsToApply.forEach((item) => current.add(item));
  } else {
    clauseIdsToApply.forEach((item) => current.delete(item));
  }
  if (!current.size) {
    const { [normalizedSpecNo]: _removed, ...rest } = normalized;
    return rest;
  }
  return {
    ...normalized,
    [normalizedSpecNo]: [...current],
  };
}

export function clearPickerClauseSelection(selectedClauseIdsBySpec, specNo = "") {
  if (!specNo) {
    return {};
  }
  const normalized = normalizePickerSelectedClauseIdsBySpec(selectedClauseIdsBySpec);
  const normalizedSpecNo = String(specNo || "").trim();
  const { [normalizedSpecNo]: _removed, ...rest } = normalized;
  return rest;
}

export function nodeIncludesDescendants(node) {
  return Boolean(node) && node.descendantsLoaded !== false;
}

export function getSelectedClauseRootIds(catalog, selectedClauseIds) {
  const selectedSet = new Set((selectedClauseIds || []).map((item) => String(item || "").trim()).filter(Boolean));
  const rootIds = new Set();
  selectedSet.forEach((clauseId) => {
    const clausePath = catalog?.byId?.[clauseId]?.clausePath || [clauseId];
    const rootId = String(clausePath[0] || clauseId).trim();
    if (rootId) {
      rootIds.add(rootId);
    }
  });
  return [...rootIds];
}

export function pruneClauseSubtreeToSelection(subtree, selectedClauseIds) {
  const selectedSet = new Set((selectedClauseIds || []).map((item) => String(item || "").trim()).filter(Boolean));

  function pruneNode(node) {
    const normalizedClauseId = String(node?.clauseId || "").trim();
    if (!normalizedClauseId) {
      return null;
    }
    if (selectedSet.has(normalizedClauseId) && areAllDescendantsSelected(node, selectedSet)) {
      return markNodeAsLoaded(node);
    }
    const children = (node.children || [])
      .map((child) => pruneNode(child))
      .filter(Boolean);
    if (!children.length) {
      return selectedSet.has(normalizedClauseId)
        ? {
            ...node,
            descendantsLoaded: false,
            children: [],
          }
        : null;
    }
    return {
      ...node,
      descendantsLoaded: false,
      children,
    };
  }

  return pruneNode(subtree);
}

export function mergeLoadedClauseRoot(roots, node) {
  const normalizedRoots = Array.isArray(roots) ? roots : [];
  const ancestorRootIndex = normalizedRoots.findIndex((root) => (
    String(root.specNo || "") === String(node.specNo || "") &&
    isPathPrefix(root.clausePath || [], node.clausePath || [])
  ));

  if (ancestorRootIndex >= 0) {
    return normalizedRoots.map((root, index) => {
      if (index !== ancestorRootIndex) {
        return root;
      }
      if (root.key === node.key) {
        return mergeNodeTrees(root, node);
      }
      return mergeNodeTrees(root, {
        ...root,
        children: [...(root.children || []), node],
      });
    });
  }

  const mergedNode = normalizedRoots.reduce((currentNode, root) => {
    if (String(root.specNo || "") !== String(node.specNo || "")) {
      return currentNode;
    }
    if (!isPathPrefix(node.clausePath || [], root.clausePath || [])) {
      return currentNode;
    }
    return mergeNodeTrees(currentNode, root);
  }, node);

  return normalizedRoots
    .filter((root) => !(
      String(root.specNo || "") === String(node.specNo || "") &&
      isPathPrefix(node.clausePath || [], root.clausePath || [])
    ))
    .concat(mergedNode);
}

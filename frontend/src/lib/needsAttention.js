// One rule for the attention icon, shared by the Dashboard and the Documents list.
export const needsAttention = (doc) =>
  Boolean(doc.hasLowConfidenceFields || doc.hasReviewWarnings);

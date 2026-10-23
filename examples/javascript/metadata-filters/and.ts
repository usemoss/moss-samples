import { runMetadataFilterExample } from "./shared";

runMetadataFilterExample({
  operator: "$and",
  description: "Use $and to require multiple metadata filters to match together.",
  query: "running shoes available in New York",
  filter: {
    $and: [
      { field: "category", condition: { $eq: "shoes" } },
      { field: "city", condition: { $eq: "new-york" } },
    ],
  },
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

import { runMetadataFilterExample } from "./shared";

runMetadataFilterExample({
  operator: "$eq",
  description: "Use $eq to match documents whose metadata field has one exact value.",
  query: "running shoes for city training",
  filter: {
    field: "category",
    condition: { $eq: "shoes" },
  },
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

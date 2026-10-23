import { runMetadataFilterExample } from "./shared";

runMetadataFilterExample({
  operator: "$near",
  description: "Use $near to match location metadata within a radius in meters.",
  query: "city products near Times Square",
  filter: {
    field: "location",
    condition: { $near: "40.7580,-73.9855,5000" },
  },
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

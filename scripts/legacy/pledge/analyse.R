#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: analyse.R <view_model.json> <output_dir>")
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("jsonlite is required")
if (!requireNamespace("ggplot2", quietly = TRUE)) stop("ggplot2 is required")

input <- jsonlite::fromJSON(args[[1]], simplifyDataFrame = TRUE)
outdir <- args[[2]]
dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
records <- input$records
stopifnot(input$contract_version == "legacy-view-v1")
stopifnot(all(records$alignment_observation_status %in% c("observed", "legacy_derived", "missing")))

qa <- as.data.frame(table(records$alignment_observation_status), stringsAsFactors = FALSE)
names(qa) <- c("alignment_observation_status", "n")
write.csv(qa, file.path(outdir, "pledge_alignment_qa.csv"), row.names = FALSE)

if (nrow(records) > 0) {
  p <- ggplot2::ggplot(records, ggplot2::aes(x = country, fill = alignment_observation_status)) +
    ggplot2::geom_bar() +
    ggplot2::labs(title = "Pledge records by country and alignment provenance", x = NULL, y = "Records") +
    ggplot2::theme_minimal()
  ggplot2::ggsave(file.path(outdir, "pledge_alignment_qa.png"), p, width = 9, height = 5)
}

cat(jsonlite::toJSON(list(contract_version=input$contract_version, rows=nrow(records), alignment_status=qa), auto_unbox=TRUE, pretty=TRUE))

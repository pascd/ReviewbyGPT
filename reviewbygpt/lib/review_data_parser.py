"""Build LLM review prompts and parse the structured responses they produce.

:class:`ReviewDataParser` is the transport-agnostic half of the review
pipeline: it doesn't care whether the response text came from OpenAI,
Ollama, or any other backend (see :class:`~reviewbygpt.lib.llm_client.
LLMClient`) -- it only builds the prompt from ``review_data.yaml`` and
parses whatever text comes back.

The parsing methods are deliberately layered with fallback strategies
(primary marker-based regex -> alternative regex -> manual scanning ->
last-resort heuristics) because LLMs don't always follow the requested
output format exactly. Each fallback is a little less strict (and a little
less reliable) than the one before it, so they're tried in that order and
the first one that finds anything is used.
"""

import logging
import re

import yaml

logger = logging.getLogger(__name__)


class ReviewDataParser:
    """Reads ``review_data.yaml`` and turns LLM responses into structured data."""

    def __init__(self, config):
        """Store the path to the review-schema YAML file.

        Args:
            config: Path to a YAML file with the keys
                ``quality_assessment_questions``, ``cutoff_score``,
                ``excluding_questions``, and ``data_extraction_fields``
                (see ``config/review_data.yaml`` for an example).
        """
        self.config = config

    def load_yaml_file(self):
        """Load and parse ``self.config`` as YAML.

        Returns:
            dict | None: The parsed YAML document, or None if it could not
            be read/parsed (the error is logged, not raised).
        """
        try:
            with open(self.config, 'r') as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.error(f"Error loading YAML file: {exc}")
            return None

    def save_yaml_file(self, data):
        """Overwrite ``self.config`` with ``data`` serialized as YAML.

        Args:
            data: The (dict-like) data structure to write.

        Returns:
            bool: True on success, False if the write/serialization failed.
        """
        try:
            with open(self.config, 'w') as stream:
                yaml.dump(data, stream)
                return True
        except yaml.YAMLError as exc:
            logger.error(f"Error saving YAML file: {exc}")
            return False

    def get_all_quality_assessment_fields(self):
        """Read the ``quality_assessment_questions`` list from the YAML config.

        Returns:
            list[dict]: One ``{"id", "question", "scores"}`` dict per
            question, or an empty list if the key is missing/invalid.
        """
        data = self.load_yaml_file()
        if not data or "quality_assessment_questions" not in data:
            logger.error("Invalid or missing quality assessment questions.")
            return []
        return [{"id": q["id"], "question": q["question"], "scores": q["scores"]} for q in data["quality_assessment_questions"]]

    def get_all_data_extraction_fields(self):
        """Read the ``data_extraction_fields`` list from the YAML config.

        Returns:
            list[dict]: One ``{"key", "description"}`` dict per field, or
            an empty list if the key is missing/invalid.
        """
        data = self.load_yaml_file()
        if not data or "data_extraction_fields" not in data:
            logger.error("Invalid or missing data extraction fields.")
            return []
        return [{"key": field["key"], "description": field["description"]} for field in data["data_extraction_fields"]]

    def get_all_excluding_questions(self):
        """Read the ``excluding_questions`` list from the YAML config.

        These are quality-assessment question IDs that cause automatic
        rejection of a paper if they score 0, regardless of total score.

        Returns:
            list[str]: The excluding question IDs, or an empty list if the
            key is missing/invalid.
        """
        data = self.load_yaml_file()
        if not data or "excluding_questions" not in data:
            logger.error("Invalid or missing excluding questions.")
            return []
        return data["excluding_questions"]

    def get_cutoff_score(self):
        """Read the ``cutoff_score`` value from the YAML config.

        Returns:
            The configured cutoff score, or 0 if not set.
        """
        data = self.load_yaml_file()
        return data.get("cutoff_score", 0)

    def get_analysis_prompt(self):
        """
        Create an analysis prompt with explicit formatting instructions
        that produce responses specifically designed for easy extraction
        """
        qa_fields = self.get_all_quality_assessment_fields()
        de_fields = self.get_all_data_extraction_fields()
        cutoff_score = self.get_cutoff_score()

        if not qa_fields or not de_fields:
            logger.error("Missing required fields for analysis prompt.")
            return ""

        # Start with clear structured instructions
        prompt = "Hello, I need you to analyze the PDF document I've uploaded. Please follow these instructions precisely:\n\n"

        # Quality Assessment section with clear formatting
        prompt += "===== PART 1: QUALITY ASSESSMENT =====\n"
        for qa in qa_fields:
            prompt += f"* {qa['id']}: {qa['question']} (Possible scores: {', '.join(map(str, qa['scores']))})\n"

        # Data Extraction section with clear formatting
        prompt += "\n===== PART 2: DATA EXTRACTION =====\n"
        for de in de_fields:
            prompt += f"* {de['key']}: {de['description']}\n"

        # Format instructions with explicit markers and examples
        prompt += f"\nMinimum acceptance score: {cutoff_score}\n\n"
        prompt += "===== OUTPUT FORMAT INSTRUCTIONS =====\n"

        # Very explicit output formatting for quality assessment
        prompt += "For Quality Assessment, follow this exact format with no deviations:\n\n"
        prompt += "==QUALITY_ASSESSMENT_START==\n"
        prompt += "QE1: [Your brief description here]\n"
        prompt += "QE1_SCORE: [score]\n\n"
        prompt += "QE2: [Your brief description here]\n"
        prompt += "QE2_SCORE: [score]\n"
        prompt += "==QUALITY_ASSESSMENT_END==\n\n"

        # Very explicit output formatting for data extraction
        prompt += "For Data Extraction, follow this exact format with no deviations:\n\n"
        prompt += "==DATA_EXTRACTION_START==\n"
        prompt += "AUTHOR: [author names]\n"
        prompt += "YEAR: [publication year]\n"
        prompt += "TITLE: [paper title]\n"
        prompt += "==DATA_EXTRACTION_END==\n\n"

        # Additional instructions with emphasis on formatting
        prompt += "IMPORTANT INSTRUCTIONS:\n"
        prompt += "1. Use EXACTLY the section markers shown above (==SECTION_START== and ==SECTION_END==)\n"
        prompt += "2. For quality assessment items, use the exact format 'QE1: [text]' followed by a line break and 'QE1_SCORE: [number]'\n"
        prompt += "3. For data extraction fields, use the exact keys I've listed, in ALL CAPS followed by a colon\n"
        prompt += "4. If information is not available, write 'Not Specified (N/S)'\n"
        prompt += "5. Do not add any additional formatting, bullets, or markdown\n"
        prompt += "6. Each item should be on its own line\n"
        prompt += "7. You should respect the line breaks here and replicate them if they exist\n"

        return prompt

    def preprocess_qa_data(self, qa_data, total_score):
        """Flatten a ``{question_id: {question_id: text, "SCORE": n}}`` dict.

        The extraction methods below build an intermediate, nested
        structure per question. This turns that into the flat
        ``{"QE1": text, "QE1_SCORE": n, ..., "TOTAL_SCORE": total}`` shape
        that :class:`~reviewbygpt.lib.excel_data_parser.ExcelDataParser`
        expects (one column per key).

        Args:
            qa_data: Mapping of question id -> nested dict (or a raw
                value, handled defensively below in case a question's
                entry isn't shaped as expected).
            total_score: The aggregate score across all questions.

        Returns:
            dict: The flattened data, including a "TOTAL_SCORE" key.
        """
        flattened_data = {}

        for qa_key, qa_info in qa_data.items():
            # Check if qa_info is a dictionary
            if isinstance(qa_info, dict):
                # Add description and score to flattened dictionary
                flattened_data[qa_key] = qa_info.get(qa_key, "")
                flattened_data[f"{qa_key}_SCORE"] = qa_info.get("SCORE", "")
            else:
                # Handle unexpected cases (e.g., if qa_info is a float or string)
                flattened_data[qa_key] = str(qa_info)
                flattened_data[f"{qa_key}_SCORE"] = ""

        # Add total score
        flattened_data["TOTAL_SCORE"] = total_score

        return flattened_data

    def get_quality_assessment_text(self, response):
        """
        Extracts quality assessment data from a response with explicit section markers
        Enhanced to handle responses without linebreaks between items
        """
        qa_data = {}
        total_score = 0

        # Look for the quality assessment section between markers
        qa_pattern = re.compile(r"==QUALITY_ASSESSMENT_START==(.*?)==QUALITY_ASSESSMENT_END==", re.DOTALL)
        qa_match = qa_pattern.search(response)

        if not qa_match:
            logger.warning("Could not find quality assessment section with markers")
            # Fall back to the original extraction method for backward compatibility
            return self._legacy_get_quality_assessment_text(response)

        # Extract the section content
        qa_content = qa_match.group(1).strip()
        logger.info(f"Found quality assessment section ({len(qa_content)} chars)")

        # Try different patterns to match QE items and scores
        # Pattern 1: Looks for QEn: [text] QEn_SCORE: [score]
        item_pattern = re.compile(r"(QE\d+):\s*(.*?)(?:\s*|\n)\1_SCORE:\s*([0-9.]+)", re.DOTALL)
        matches = item_pattern.findall(qa_content)

        if not matches:
            # Pattern 2: Alternative approach for more challenging formats.
            # Some models omit the line breaks the prompt asked for, which
            # breaks Pattern 1's `\1_SCORE:` backreference; fall back to
            # locating each "QEn:"/"QEn_SCORE:" marker by string position
            # instead of relying on regex backreferences.
            logger.warning("Using alternative pattern for QA extraction")

            # Try to extract all QE IDs
            qe_ids = re.findall(r'(QE\d+):', qa_content)

            # For each QE ID, extract the description and score
            for qe_id in qe_ids:
                # Find where this QE ID starts
                qe_start = qa_content.find(f"{qe_id}:")
                if qe_start == -1:
                    continue

                # Find where the description ends (either at next QE or at score)
                next_qe_start = -1
                for next_id in qe_ids:
                    if next_id != qe_id:
                        pos = qa_content.find(f"{next_id}:", qe_start + len(qe_id) + 1)
                        if pos != -1 and (next_qe_start == -1 or pos < next_qe_start):
                            next_qe_start = pos

                score_marker = f"{qe_id}_SCORE:"
                score_pos = qa_content.find(score_marker, qe_start)

                if score_pos == -1:
                    logger.warning(f"Could not find score for {qe_id}")
                    continue

                # Extract description (from after QE ID to before score or next QE)
                desc_start = qe_start + len(qe_id) + 1
                desc_end = score_pos if next_qe_start == -1 or score_pos < next_qe_start else next_qe_start
                description = qa_content[desc_start:desc_end].strip()

                # Extract score
                score_start = score_pos + len(score_marker)
                score_end = qa_content.find(' ', score_start)
                if score_end == -1:
                    score_text = qa_content[score_start:].strip()
                else:
                    score_text = qa_content[score_start:score_end].strip()

                try:
                    score = float(score_text)
                    qa_data[qe_id] = {
                        f"{qe_id}": description.replace('"', ""),
                        "SCORE": score
                    }
                    total_score += score
                    logger.info(f"Extracted {qe_id} with score {score}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert score to float for {qe_id}: {score_text}")
        else:
            # Process matches from the first pattern
            for match in matches:
                question_id, description, score = match
                try:
                    score = float(score.strip())
                    qa_data[question_id] = {
                        f"{question_id}": description.strip().replace('"', ""),
                        "SCORE": score
                    }
                    total_score += score
                    logger.info(f"Extracted {question_id} with score {score}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert score to float for {question_id}: {score}")

        # Add total score
        qa_data["TOTAL_SCORE"] = total_score
        logger.info(f"Total QA score: {total_score}")

        return self.preprocess_qa_data(qa_data, total_score)

    def _legacy_get_quality_assessment_text(self, response):
        """
        Legacy method for extracting quality assessment data from responses without markers.

        Used only as a fallback when ``get_quality_assessment_text`` can't
        find the ``==QUALITY_ASSESSMENT_START==``/``==_END==`` markers at
        all -- i.e. the model ignored the requested section markers
        entirely. This looser pattern accepts "QEn Score"/"QEnScore"/
        "QEn_SCORE" variants without needing the markers.
        """
        qa_data = {}
        total_score = 0

        qa_pattern = re.compile(r"(QE\d+)[:\.]?\s*(.*?)\s*(?:QE\d+\s*Score|QE\d+Score|QE\d+_SCORE)[:\.]?\s*([0-9.]+)", re.DOTALL)
        matches = qa_pattern.findall(response)

        for match in matches:
            question_id, description, score = match
            score = float(score.strip())
            qa_data[question_id] = {
                f"{question_id}": description.strip().replace('"', ""),
                "SCORE": score
            }
            total_score += score

        # Add total score
        qa_data["TOTAL_SCORE"] = total_score

        return self.preprocess_qa_data(qa_data, total_score)

    def get_data_extraction_text(self, response):
        """
        Extracts data extraction fields from a response with explicit section markers
        Enhanced to handle responses without proper linebreaks
        """
        de_data = {}

        # Look for the data extraction section between markers
        de_pattern = re.compile(r"==DATA_EXTRACTION_START==(.*?)==DATA_EXTRACTION_END==", re.DOTALL)
        de_match = de_pattern.search(response)

        if not de_match:
            logger.warning("Could not find data extraction section with markers")
            # Fall back to the original extraction method for backward compatibility
            return self._legacy_get_data_extraction_text(response)

        # Extract the section content
        de_content = de_match.group(1).strip()
        logger.info(f"Found data extraction section ({len(de_content)} chars)")

        # First method: Pattern matching for field extraction
        # This looks for uppercase keys followed by a colon and value
        # Modified pattern that allows uppercase letters in values
        field_pattern = re.compile(r"([A-Z][A-Z\s]+(?:\sOF\s[A-Z]+)?)\s*:\s*(.*?)(?=\s+[A-Z][A-Z\s]+(?:\sOF\s[A-Z]+)?:|$)", re.DOTALL)
        matches = field_pattern.findall(de_content)

        if matches:
            # Process the matches using the pattern
            for key, value in matches:
                key = key.strip()
                value = value.strip()

                logger.info(f"Extracted field with pattern: '{key}' = '{value}'")
                de_data[key] = value
        else:
            # Second method: Manual extraction by finding all uppercase fields.
            # Used when the regex above finds no matches at all -- typically
            # because a value itself contains a run of uppercase text that
            # confuses the lookahead. This walks the potential "KEY:" markers
            # by string position instead.
            logger.warning("Using manual extraction for data fields")

            # Get all potential field keys (uppercase followed by colon)
            potential_keys = re.findall(r'([A-Z][A-Z\s]+(?:\sOF\s[A-Z]+)?)\s*:', de_content)

            if potential_keys:
                # For each key, extract the text until the next key
                for i, key in enumerate(potential_keys):
                    # Find where this key appears in the content
                    key_pos = de_content.find(f"{key}:")
                    if key_pos == -1:
                        continue

                    # Determine where the value ends (at next key or end of content)
                    value_start = key_pos + len(key) + 1  # +1 for the colon
                    value_end = len(de_content)

                    # Find position of next key if there is one
                    if i < len(potential_keys) - 1:
                        next_key = potential_keys[i+1]
                        next_key_pos = de_content.find(f"{next_key}:", value_start)
                        if next_key_pos != -1:
                            value_end = next_key_pos

                    # Extract the value
                    value = de_content[value_start:value_end].strip()

                    # Store the result
                    key = key.strip()
                    logger.info(f"Manually extracted field: '{key}' = '{value}'")
                    de_data[key] = value
            else:
                # Third method: Split by obvious separators. Last resort when
                # no "KEY:"-shaped markers were found at all.
                logger.warning("No data extraction fields found with pattern or manual extraction.")

                # Try a very simple split by colon approach for last resort
                parts = de_content.split(':')
                if len(parts) > 1:
                    for i in range(len(parts) - 1):  # Exclude the last part which wouldn't have a value
                        # The key is the end of the previous part, or the beginning if it's the first
                        key_part = parts[i].strip()
                        # Look for uppercase words at the end which might be a key
                        key_match = re.search(r'([A-Z][A-Z\s]+)$', key_part)
                        if key_match:
                            key = key_match.group(1).strip()
                            # The value is the beginning of the next part before any uppercase words
                            value_part = parts[i+1]
                            value_match = re.search(r'^(.*?)(?=[A-Z][A-Z\s]+:|$)', value_part, re.DOTALL)
                            if value_match:
                                value = value_match.group(1).strip()
                                logger.info(f"Basic split extracted: '{key}' = '{value}'")
                                de_data[key] = value

        # If there's content but no keys were extracted, try one more approach
        if de_content and not de_data:
            logger.warning("Attempting final emergency extraction method")
            # This is a last resort: look for any text that might be a title
            title_match = re.search(r'TITLE\s*:(.*?)(?=\s[A-Z]{2,}|$)', de_content, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
                de_data["TITLE"] = title
                logger.info(f"Emergency extraction found title: {title}")

        logger.info(f"Total data extraction fields: {len(de_data)}")
        return de_data

    def _legacy_get_data_extraction_text(self, response):
        """
        Legacy method for extracting data extraction fields from responses without markers.

        Used only as a fallback when ``get_data_extraction_text`` can't find
        the ``==DATA_EXTRACTION_START==``/``==_END==`` markers -- i.e. the
        model ignored the requested section markers. Locates a
        "Data Extraction" heading instead and parses simple "Key: value"
        lines until a plausible end-of-section marker.
        """
        de_data = {}

        # First find where "Data Extraction" appears in the text
        extraction_markers = [
            "Data Extraction",
            "Data Extraction:",
            "Data Extraction\n",
            "Data Extraction:\n"
        ]

        start_idx = -1
        for marker in extraction_markers:
            if marker in response:
                start_idx = response.find(marker) + len(marker)
                logger.info(f"Found marker '{marker}' at position {start_idx - len(marker)}")
                break

        if start_idx == -1:
            logger.error("Could not find Data Extraction section in response")
            return de_data

        # Find where the data extraction section ends
        end_markers = [
            "Minimum acceptance score",
            "SECTION 3",
            "Cutoff Score",
            "\n\n\n"
        ]

        end_idx = len(response)
        for marker in end_markers:
            pos = response.find(marker, start_idx)
            if pos != -1 and pos < end_idx:
                end_idx = pos
                logger.info(f"Found end marker '{marker}' at position {pos}")

        # Extract the data extraction section
        data_section = response[start_idx:end_idx].strip()

        # Process line by line
        lines = data_section.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip the header line if it contains only "Data Extraction"
            if line.lower() == "data extraction":
                continue

            # Check for key-value separator
            if ":" in line:
                parts = line.split(":", 1)
                key = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ""

                # Clean up the key and value
                key = key.replace('"', "").replace("*", "").strip()
                value = value.replace('"', "").strip()

                if key:
                    de_data[key] = value

        return de_data

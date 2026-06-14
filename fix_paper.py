import re

with open("paper/paper.md", "r", encoding="utf-8") as f:
    text = f.read()

# 1. Add short_title
text = text.replace(
    "title: 'SynaptiPy: An Open-Source Electrophysiology Visualization and Analysis Suite'",
    "title: 'SynaptiPy: An Open-Source Electrophysiology Visualization and Analysis Suite'\nshort_title: 'SynaptiPy'",
)

# 2. Remove TODO block
text = re.sub(r"<!--.*?MANUSCRIPT TODO.*?END TODO.*?-->\n+", "", text, flags=re.DOTALL)

# 3. Fix broken sentence in Methods
text = text.replace("dynamically generate Software Architecture", "dynamically generate graphical user interfaces.")

# 4. Fix heading numbers
text = text.replace(
    "### 1. Extensible Data Parsing and Software Maintenance", "### 2. Extensible Data Parsing and Software Maintenance"
)

# 5. Fix duplicated Table 2 blocks
# We'll locate the first occurrence of Table 2 footnote and strip everything after it up to "### 3. High-Throughput"
table2_start = "**Extended Data Table 2:"
idx1 = text.find(table2_start)
if idx1 != -1:
    # Find the FIRST footnote for Table 2
    idx2 = text.find("*Values from BatchAnalysisEngine", idx1)
    if idx2 != -1:
        # Find the end of this footnote (next double newline)
        idx_end_footnote = text.find("\n\n", idx2)
        if idx_end_footnote != -1:
            # Find where the next section begins
            idx_next_section = text.find("### 3. High-Throughput")
            if idx_next_section != -1:
                # Remove everything between the end of the first footnote and the start of the next section
                text = text[:idx_end_footnote] + "\n\n" + text[idx_next_section:]

# 6. Fix Discussion format
old_discussion = """# Discussion (Comparison to Existing Tools)
Within the current landscape of intracellular electrophysiology software, SynaptiPy provides a distinct analytical utility:
* **Commercial Software (e.g., Clampfit):** While considered an industry standard, proprietary applications offer limited programmatic flexibility for high-throughput batch analysis. SynaptiPy provides comparable analytical rigor alongside comprehensive automation and an open-source (AGPL-3.0) license.
* **Programmatic Libraries (e.g., eFEL, IPFX):** Libraries such as the Electrophysiology Feature Extraction Library (eFEL) ([Blue Brain Project, 2024](#ref-efel_bbp)) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX) offer robust programmatic spike analysis for modeling datasets, but generally lack an interactive graphical interface for visual verification on raw, noisy recordings. SynaptiPy integrates these high-throughput programmatic strengths into a cohesive visual platform utilizing experimental-grade algorithms.
* **GUI-Based Open-Source Applications (e.g., Stimfit):** Stimfit ([Guzman et al., 2014](#ref-guzman_stimfit_2014)) provides a highly respected C++ application; however, extending its functionality requires low-level programming expertise. SynaptiPy relies entirely on a Python-based architecture for simplified extensibility and includes native integration with modern NWB standards."""

new_discussion = """# Discussion

Within the current landscape of intracellular electrophysiology software, SynaptiPy provides a distinct analytical utility. While commercial software packages like Clampfit remain industry standards, their proprietary nature limits programmatic flexibility for high-throughput batch analysis. SynaptiPy addresses this by providing comparable analytical rigor alongside comprehensive automation and an open-source (AGPL-3.0) license. 

When compared to programmatic libraries such as the Electrophysiology Feature Extraction Library (eFEL) [(Blue Brain Project, 2024)](#ref-efel_bbp) and the Allen Institute's Intrinsic Physiology Feature Extractor (IPFX), these existing tools offer robust spike analysis for modeling datasets, but generally lack an interactive graphical interface for visual verification on raw, noisy recordings. SynaptiPy integrates these high-throughput programmatic strengths into a cohesive visual platform utilizing experimental-grade algorithms. 

Furthermore, relative to GUI-based open-source applications like Stimfit [(Guzman et al., 2014)](#ref-guzman_stimfit_2014), which provides a highly respected C++ application, extending such software requires low-level programming expertise. SynaptiPy relies entirely on a Python-based architecture for simplified extensibility and includes native integration with modern NWB standards, significantly lowering the barrier to entry for experimental neuroscientists."""

text = text.replace(old_discussion, new_discussion)

# 7. Fix Data Availability & Add COI / Acknowledgments
old_availability = """## Data and Code Availability
In accordance with *eNeuro* guidelines for reproducible research, the source code and exact software version described in this manuscript are permanently archived on Zenodo at **DOI: [Zenodo DOI Placeholder]**. All biological data arrays used to generate the validation and performance figures (e.g., `2023_04_11_0021.abf`) are available within the open-source repository's `examples/data/` structure to ensure complete reproducibility of the described algorithms."""

new_availability = """## Data and Code Availability
In accordance with *eNeuro* guidelines for reproducible research, the source code and exact software version described in this manuscript will be permanently archived on Zenodo upon publication. All biological data arrays used to generate the validation and performance figures (e.g., `2023_04_11_0021.abf`) are available within the open-source repository's `examples/data/` structure to ensure complete reproducibility of the described algorithms.

# Conflict of Interest
The authors declare no competing financial interests.

# Acknowledgments
We thank the open-source scientific Python community for maintaining the foundational libraries that make this software possible."""

text = text.replace(old_availability, new_availability)

# 8. Globally fix citations format from ([Author, Year](#ref)) to [(Author, Year)](#ref)
text = re.sub(r"\(\[([^\]]+)\]\(#ref-([^\)]+)\)\)", r"[(\1)](#ref-\2)", text)

with open("paper/paper.md", "w", encoding="utf-8") as f:
    f.write(text)

print("paper.md successfully fixed.")

#!/usr/bin/env python3
"""
Retrieval engine for sparse-feedback research backend.
Retrieves relevant constraints, anti-goals, and heuristics for a given case.
"""

import json
import argparse
from typing import Dict, List, Set

def load_rules(filepath: str = "rules.json") -> Dict:
    """Load distilled rules from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)

def load_cases(filepath: str = "cases.json") -> Dict[str, Dict]:
    """Load cases data."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return {case['case_id']: case for case in data['cases']}

def extract_case_keywords(case: Dict) -> Set[str]:
    """Extract keywords from case context and candidate summaries."""
    keywords = set()
    
    # Extract from context
    context_words = case['context'].lower().split()
    keywords.update(context_words)
    
    # Extract from candidate summaries
    for candidate_key in ['candidate_a', 'candidate_b']:
        if candidate_key in case:
            summary = case[candidate_key]['summary'].lower()
            summary_words = summary.split()
            keywords.update(summary_words)
    
    # Clean and filter keywords
    cleaned_keywords = set()
    for word in keywords:
        # Remove punctuation and filter short words
        clean_word = ''.join(c for c in word if c.isalnum()).lower()
        if len(clean_word) > 2:
            cleaned_keywords.add(clean_word)
    
    return cleaned_keywords

def calculate_keyword_overlap(case_keywords: Set[str], rule_keywords: List[str]) -> float:
    """Calculate overlap score between case keywords and rule keywords."""
    if not rule_keywords:
        return 0.0
    
    rule_keywords_set = set(kw.lower() for kw in rule_keywords)
    overlap = len(case_keywords & rule_keywords_set)
    
    # Normalize by rule keywords count 
    return overlap / len(rule_keywords_set) if rule_keywords_set else 0.0

def calculate_attribute_relevance(case: Dict, rule: Dict) -> float:
    """Calculate how relevant a rule is based on case attributes."""
    relevance_score = 0.0
    
    # Check if rule type matches case characteristics
    rule_type = rule.get('type', '')
    
    # Get average values for both candidates
    attrs = ['temporal_consistency', 'spatial_compactness', 'peak_strength', 'clutter_level']
    case_attrs = {}
    
    for attr in attrs:
        values = []
        for candidate_key in ['candidate_a', 'candidate_b']:
            if candidate_key in case and attr in case[candidate_key]:
                values.append(case[candidate_key][attr])
        if values:
            case_attrs[attr] = sum(values) / len(values)
    
    # Rule-specific relevance scoring
    if 'temporal' in rule_type and 'temporal_consistency' in case_attrs:
        # More relevant if case has temporal consistency issues
        relevance_score += (1.0 - case_attrs['temporal_consistency']) * 0.8
    
    if 'spatial' in rule_type and 'spatial_compactness' in case_attrs:
        # More relevant if case has spatial compactness issues
        relevance_score += (1.0 - case_attrs['spatial_compactness']) * 0.8
    
    if 'clutter' in rule_type and 'clutter_level' in case_attrs:
        # More relevant if case has high clutter
        relevance_score += case_attrs['clutter_level'] * 0.9
    
    return min(relevance_score, 1.0)  # Cap at 1.0

def retrieve_relevant_rules(case_id: str, rules: Dict, cases: Dict, top_k: int = 5) -> Dict:
    """Retrieve most relevant rules for a given case."""
    if case_id not in cases:
        raise ValueError(f"Case {case_id} not found")
    
    case = cases[case_id]
    case_keywords = extract_case_keywords(case)
    
    # Score all rules
    scored_rules = {
        'constraints': [],
        'anti_goals': [], 
        'heuristics': []
    }
    
    for rule_type in ['constraints', 'anti_goals', 'heuristics']:
        for rule in rules[rule_type]:
            # Calculate relevance scores
            keyword_score = calculate_keyword_overlap(case_keywords, rule.get('keywords', []))
            attribute_score = calculate_attribute_relevance(case, rule)
            
            # Combined relevance score
            relevance_score = (keyword_score * 0.4) + (attribute_score * 0.6)
            
            scored_rule = rule.copy()
            scored_rule['relevance_score'] = relevance_score
            scored_rule['keyword_overlap'] = keyword_score
            scored_rule['attribute_relevance'] = attribute_score
            
            scored_rules[rule_type].append(scored_rule)
    
    # Sort by relevance and take top_k
    for rule_type in scored_rules:
        scored_rules[rule_type] = sorted(
            scored_rules[rule_type], 
            key=lambda x: x['relevance_score'], 
            reverse=True
        )[:top_k]
    
    return {
        'case_id': case_id,
        'case_context': case['context'],
        'retrieved_rules': scored_rules,
        'case_keywords': list(case_keywords),
        'retrieval_summary': {
            'constraints_retrieved': len([r for r in scored_rules['constraints'] if r['relevance_score'] > 0]),
            'anti_goals_retrieved': len([r for r in scored_rules['anti_goals'] if r['relevance_score'] > 0]), 
            'heuristics_retrieved': len([r for r in scored_rules['heuristics'] if r['relevance_score'] > 0])
        }
    }

def print_retrieval_results(results: Dict):
    """Print retrieval results in a readable format."""
    print(f"🔍 RULE RETRIEVAL FOR CASE: {results['case_id']}")
    print("=" * 60)
    print(f"📋 Context: {results['case_context']}")
    print(f"🏷️  Case Keywords: {', '.join(results['case_keywords'][:10])}...")
    print()
    
    summary = results['retrieval_summary']
    print(f"📊 Retrieved {summary['constraints_retrieved']} constraints, "
          f"{summary['anti_goals_retrieved']} anti-goals, "
          f"{summary['heuristics_retrieved']} heuristics")
    print()
    
    for rule_type, display_name in [
        ('constraints', '🔒 RELEVANT CONSTRAINTS'),
        ('anti_goals', '🚫 RELEVANT ANTI-GOALS'),
        ('heuristics', '💡 RELEVANT HEURISTICS')
    ]:
        rules_list = results['retrieved_rules'][rule_type]
        relevant_rules = [r for r in rules_list if r['relevance_score'] > 0]
        
        if relevant_rules:
            print(f"{display_name}:")
            for i, rule in enumerate(relevant_rules, 1):
                print(f"  {i}. {rule['description']}")
                print(f"     Relevance: {rule['relevance_score']:.3f} "
                      f"(keyword: {rule['keyword_overlap']:.3f}, "
                      f"attribute: {rule['attribute_relevance']:.3f})")
                print(f"     Source: {rule['source_case']}")
                print()

def main():
    """Main retrieval workflow."""
    parser = argparse.ArgumentParser(description="Retrieve relevant rules for a case")
    parser.add_argument("case_id", help="Case ID to retrieve rules for")
    parser.add_argument("--top-k", type=int, default=5, help="Maximum rules to retrieve per type")
    
    args = parser.parse_args()
    
    # Load data
    try:
        rules = load_rules()
        cases = load_cases()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Make sure to run 'python distill.py' first to generate rules.json")
        return
    
    # Retrieve relevant rules
    try:
        results = retrieve_relevant_rules(args.case_id, rules, cases, args.top_k)
        print_retrieval_results(results)
        return results
    except ValueError as e:
        print(f"Error: {e}")
        available_cases = list(cases.keys())
        print(f"Available cases: {', '.join(available_cases)}")

if __name__ == "__main__":
    main()